"""Web tier: serves the UI and streams answers.

WHY THIS FILE EXISTS SEPARATELY FROM pipeline.py
Render task runs cannot accept inbound connections (no ports), so the workflow
can never serve the UI. Two services are mandatory:
  this web tier  ->  triggers runs  ->  Render Workflow (compute)

TWO KINDS OF BRAIN, ONE DASHBOARD
`COGNEE_DATASET` is the pre-built demo brain. Anything a user uploads becomes a
NEW dataset addressed by name. So every read route takes an optional `dataset`
parameter, and one UI serves all of them.

The fixture fallback is deliberately scoped to the demo brain only. The snapshot
in fixtures/graph.json is a copy of the DEMO graph, so serving it under a user's
brain would be a fabricated result presented as a real one - worse than an
honest empty state. Same reason the mock provider refuses to answer for an
uploaded brain.
"""

import asyncio
import json
import os
import re
import time
from pathlib import Path

# --- environment must load BEFORE memory_layer is imported ---------------
# memory_layer reads PROVIDER at import time, so a .env loaded afterwards
# would silently be ignored and the app would fall back to the mock provider.
HERE = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(HERE, ".env"))
except ImportError:  # dotenv is optional; env vars still work
    pass

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

import documents  # noqa: E402
import memory_layer  # noqa: E402
from memory_layer import recall  # noqa: E402

app = FastAPI(title="Kestrel Company Brain")

# One shared stylesheet and sidebar for every page. Serving them from /static
# means the shell is written once instead of pasted into four HTML files.
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")

GRAPH_FIXTURE = os.path.join(HERE, "fixtures", "graph.json")
# Per-brain snapshots, written by snapshot.py. Committed, so a deployment with
# no tenant can still serve every brain rather than only the demo.
BRAINS_DIR = Path(HERE) / "fixtures" / "brains"

# Single source of truth for "which brain is the demo".
DEMO_DATASET = memory_layer.default_dataset()

# Names become dataset names on the tenant and appear in API paths, so keep them
# boring. Normalised rather than rejected where possible: a user typing
# "Acme Corp!" should get acme_corp, not an error.
BRAIN_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_]{2,39}$")
RESERVED_NAMES = {DEMO_DATASET, "default_dataset", "company_brain"}


def normalize_brain_name(raw: str) -> str:
    """Turn whatever the user typed into a safe dataset name.

    Returns "" when nothing usable is left, so the caller can reject with a
    clear message instead of creating a dataset called "-".
    """
    name = (raw or "").strip().lower()
    name = re.sub(r"[\s\-.]+", "_", name)          # spaces, dots, dashes -> _
    name = re.sub(r"[^a-z0-9_]", "", name)         # drop anything else
    name = re.sub(r"_{2,}", "_", name).strip("_")  # collapse and trim
    return name if BRAIN_NAME_RE.match(name) else ""


def _pipeline_state(payload) -> str:
    """Pull one readable state out of Cognee's per-dataset status map.

    The payload is keyed by dataset UUID:
        {"<uuid>": {"status": "DATASET_PROCESSING_STARTED", ...}}
    Flattening it here means the UI never has to know that shape, and the
    progress log shows real pipeline states instead of a nested dict.
    """
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, dict) and value.get("status"):
                return str(value["status"])
        if payload.get("status"):
            return str(payload["status"])
    return "working"


def _failure_detail(payload) -> str:
    """Best-effort human explanation of a failed pipeline, for the UI.

    Without this the user is told only "it failed", which is barely better than
    being told nothing. Cognee puts the reason in different keys depending on
    where it failed, so check the useful ones in order.
    """
    keys = ("error", "error_detail", "reason", "message")
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, dict):
                for key in keys:
                    text = value.get(key)
                    if isinstance(text, str) and text.strip():
                        return text.strip()[:300]
        for key in keys:
            text = payload.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()[:300]
    return "The ingestion pipeline reported a failure."


async def _read_capped(upload: UploadFile, limit: int) -> bytes:
    """Read an upload in chunks, refusing as soon as it exceeds `limit`.

    The old code did `await f.read()` for every file and only THEN checked the
    size, so the whole payload was already resident in memory before any limit
    applied — an easy way to OOM the container. Aborting mid-read means a 5 GB
    upload costs one chunk, not five gigabytes of RAM.
    """
    chunks = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"{upload.filename or 'file'} exceeds the "
                    f"{limit // 1_048_576} MB per-file limit."
                ),
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _load_graph(dataset: str | None = None):
    """Return (graph, source) — live from the tenant, else a committed snapshot.

    Snapshots are per-brain (`fixtures/brains/<name>.json`, written by
    snapshot.py). Each file is that brain's OWN data, so the honesty rule still
    holds: a snapshot is never served for a brain it does not describe, because
    a fabricated graph looks exactly like a real one.

    `fixtures/graph.json` is the original single-brain snapshot and is still
    honoured for the demo, so an older checkout keeps working.
    """
    target = dataset or DEMO_DATASET
    cloud_error = None

    try:
        import cognee_cloud

        return cognee_cloud.graph(target), "cloud"
    except Exception as exc:  # noqa: BLE001
        cloud_error = str(exc)[:200]

    candidates = [BRAINS_DIR / f"{target}.json"]
    if target == DEMO_DATASET:
        candidates.append(GRAPH_FIXTURE)   # legacy single-brain snapshot

    for path in candidates:
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh), "fixture"
        except FileNotFoundError:
            continue
        except Exception as exc:  # noqa: BLE001
            cloud_error = f"{cloud_error}; {path.name}: {exc}"[:300]

    return None, f"cloud: {cloud_error}"[:300]


def _offline_brains() -> list:
    """Every brain we hold a snapshot for, read from the export manifest."""
    try:
        with open(BRAINS_DIR / "index.json", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except Exception:  # noqa: BLE001
        return []
    return [
        {
            "name": name,
            "id": None,
            "is_demo": name == DEMO_DATASET,
            "is_system": name == "default_dataset",
            "nodes": info.get("nodes"),
            "edges": info.get("edges"),
        }
        for name, info in sorted((manifest.get("brains") or {}).items())
    ]


# --------------------------------------------------------------------------
# health
# --------------------------------------------------------------------------

@app.get("/health")
def health():
    """Always have this. A health endpoint means the demo never looks dead."""
    payload = {
        "ok": True,
        "provider": memory_layer.PROVIDER,
        "dataset": DEMO_DATASET,
        "service": os.getenv("COGNEE_SERVICE_URL", ""),
    }
    # Prove the tenant instance is actually reachable, not just configured.
    if payload["provider"] == "cloud":
        try:
            import cognee_cloud

            upstream = cognee_cloud.health()
            payload["upstream"] = upstream.get("status", "unknown")
            payload["components"] = {
                k: v.get("status") for k, v in (upstream.get("components") or {}).items()
            }

            # The tenant's /health endpoint is UNAUTHENTICATED. It therefore
            # reports "healthy" even when our API key is wrong — we verified
            # this by pointing the app at a bad key and watching /health claim
            # everything was fine while every query returned 401. So probe an
            # authenticated endpoint too, or this check is worse than useless.
            try:
                cognee_cloud.datasets()
                payload["auth"] = "ok"
            except Exception as exc:  # noqa: BLE001
                payload["auth"] = "failed"
                payload["auth_error"] = str(exc)[:160]
        except Exception as exc:  # noqa: BLE001 - health must never raise
            payload["upstream"] = "unreachable"
            payload["upstream_error"] = str(exc)[:200]
    return payload


# --------------------------------------------------------------------------
# read path — every route accepts an optional dataset
# --------------------------------------------------------------------------

@app.get("/api/ask")
async def ask(q: str, dataset: str | None = None, context: str | None = None):
    """Stream the answer as newline-delimited JSON so the UI never sits blank.

    `context` carries the preceding turns of the conversation. It is prepended
    to the question so a follow-up ("and who signs it off?") is resolved against
    what was already asked — without it, every turn is a cold start and a
    follow-up question has no referent.
    """
    question = q if not context else f"{context.strip()}\n\nFollow-up question: {q}"

    async def gen():
        yield json.dumps({"stage": "start", "dataset": dataset or DEMO_DATASET}) + "\n"
        try:
            async for event in recall(question, dataset):
                yield json.dumps(event) + "\n"
        except Exception as exc:  # noqa: BLE001 - demo must never white-screen
            yield json.dumps({"stage": "error", "message": str(exc)}) + "\n"
        yield json.dumps({"stage": "done"}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.get("/api/graph")
def graph(dataset: str | None = None):
    """The knowledge graph, for the graph view."""
    g, source = _load_graph(dataset)
    if g is None:
        return {"error": source, "nodes": [], "edges": []}
    g["source"] = source
    return g


@app.get("/api/stats")
def stats(dataset: str | None = None):
    """Graph size — cheap numbers that make the graph feel real.

    Uses /graph rather than /graph-summary: the summary endpoint returns
    numNodes 0 until a summary run has been computed, which would render as
    a confidently empty graph.
    """
    target = dataset or DEMO_DATASET
    g, source = _load_graph(target)
    if g is None:
        return {"ok": False, "error": source, "dataset": target, "source": "none"}
    return {
        "ok": True,
        "nodes": len(g.get("nodes", [])),
        "edges": len(g.get("edges", [])),
        "dataset": target,
        "source": source,
        "is_demo": target == DEMO_DATASET,
    }


# --------------------------------------------------------------------------
# write path — creating a brain from uploaded documents
# --------------------------------------------------------------------------

@app.get("/api/brains")
def list_brains():
    """Every brain on the tenant. Sizes are fetched per row by the dashboard."""
    if memory_layer.PROVIDER != "cloud":
        # Offline: list the brains we hold committed snapshots for, rather than
        # an empty list. A deployment with no tenant should still be able to
        # browse and query every brain that was exported.
        brains = _offline_brains()
        return {
            "ok": True,
            "provider": "mock",
            "brains": brains,
            "demo": DEMO_DATASET,
            "note": (
                "Offline mode: showing committed snapshots. Uploads need "
                "PROVIDER=cloud."
            ) if brains else "Offline mode: no snapshots found. Run snapshot.py.",
        }
    try:
        import cognee_cloud

        brains = [
            {
                "name": d.get("name"),
                "id": d.get("id"),
                "is_demo": d.get("name") == DEMO_DATASET,
                # Cognee ships an internal default dataset. It is real but it is
                # not something a user created, so the UI labels it rather than
                # offering it as a peer of their own brains.
                "is_system": d.get("name") == "default_dataset",
            }
            for d in cognee_cloud.datasets()
        ]
        brains.sort(key=lambda b: (not b["is_demo"], b["name"] or ""))
        return {"ok": True, "provider": "cloud", "brains": brains, "demo": DEMO_DATASET}
    except Exception as exc:  # noqa: BLE001
        # The tenant is unreachable. Fall back to the brains we hold snapshots
        # for rather than showing an empty list - the graphs for those brains
        # still work, so an empty list is both wrong and alarming.
        offline = _offline_brains()
        return {
            "ok": bool(offline),
            "provider": "cloud (unreachable)",
            "error": str(exc)[:200],
            "brains": offline,
            "demo": DEMO_DATASET,
            "note": "Tenant unreachable - showing committed snapshots.",
        }


@app.post("/api/brains")
async def create_brain(
    name: str = Form(...),
    files: list[UploadFile] = File(...),
    append: bool = Form(False),
):
    """Create a brain from uploaded documents, or add to an existing one.

    `append=False` (the default) refuses an existing name with 409: silently
    merging into a brain the user believes is new would produce answers from
    documents they never saw. `append=True` is the explicit opt-in — the user
    has been told the brain exists and chose to add to it.

    Order matters: validate the name BEFORE touching the tenant, and never
    write to the demo dataset.
    """
    if memory_layer.PROVIDER != "cloud":
        raise HTTPException(
            status_code=400,
            detail=(
                "Uploads need the cloud provider. This instance is running "
                "PROVIDER=mock, which has no storage - only the offline demo "
                "fixtures."
            ),
        )

    safe = normalize_brain_name(name)
    if not safe:
        raise HTTPException(
            status_code=400,
            detail=(
                "Brain name must be 3-40 characters, using letters, numbers or "
                "underscores."
            ),
        )
    if safe in RESERVED_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"'{safe}' is reserved. Please choose another name.",
        )

    import cognee_cloud

    # Refuse to merge into an existing brain UNLESS the caller explicitly asked
    # to. Silently appending to a brain the user thinks is new would produce
    # answers from documents they never saw — so the 409 is the default, and
    # `append=True` is the opt-in the UI offers once the user has been told.
    already_exists = cognee_cloud.exists(safe)
    if already_exists and not append:
        raise HTTPException(
            status_code=409,
            detail=(
                f"A brain called '{safe}' already exists. Add to it instead, "
                "or pick another name."
            ),
        )

    # Cap the count before reading anything, then cap each file WHILE reading it.
    if len(files) > documents.MAX_FILES:
        raise HTTPException(
            status_code=413,
            detail=f"Too many files: {len(files)}. The limit is {documents.MAX_FILES}.",
        )

    payload = [
        (upload.filename or "untitled", await _read_capped(upload, documents.MAX_FILE_BYTES))
        for upload in files
    ]
    if not payload:
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    # Parsing a PDF or DOCX is CPU-bound and synchronous. Running it inline in an
    # async handler stalls the entire event loop, including /health — which Render
    # uses as a liveness probe, so a slow parse could get the service restarted
    # mid-demo. Push it to a worker thread.
    docs, failures = await asyncio.to_thread(documents.extract_many, payload)
    if not docs:
        detail = "; ".join(f"{f['name']}: {f['error']}" for f in failures[:5])
        raise HTTPException(
            status_code=400,
            detail=f"None of the files could be read. {detail}",
        )

    async def ingest(doc: dict) -> dict:
        try:
            # Pass the real filename so this brain's citations can name the file
            # the user uploaded, rather than a generated text_<hash>.
            await memory_layer.remember(doc["text"], safe, doc["name"])
            return {"name": doc["name"], "ok": True, "chars": doc["chars"]}
        except Exception as exc:  # noqa: BLE001 - report, never abort the batch
            return {"name": doc["name"], "ok": False, "error": str(exc)[:200]}

    results = await asyncio.gather(*(ingest(d) for d in docs))

    succeeded = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]

    # A batch where nothing landed is not a created brain. This used to return
    # 200 with "ok": true, and `chars` summed EVERY extracted document including
    # the failed ones — so the UI printed "created with 0 document(s), 4,231
    # characters" and linked to a dashboard that could not answer anything.
    if not succeeded:
        reasons = "; ".join(
            f"{r['name']}: {r.get('error', 'unknown error')}" for r in failed[:5]
        )
        raise HTTPException(
            status_code=502,
            detail=f"None of the documents could be ingested. {reasons}",
        )

    # Record which filenames went into this brain so its answers can cite the
    # files the user actually chose. The tenant will not store document names
    # for us — `remember` accepts a `filename` field and silently ignores it —
    # so this local manifest is the only way an uploaded brain can cite itself.
    try:
        import citations

        await asyncio.to_thread(citations.record_upload, safe, docs)
    except Exception:  # noqa: BLE001 - never fail a successful upload over this
        pass

    return {
        "ok": not failed,
        "partial": bool(failed),
        "name": safe,
        # Lets the UI say "added to" rather than "created" — the two read very
        # differently when the user has just extended an existing brain.
        "appended": already_exists,
        "documents": len(succeeded),
        # Count only what was actually stored, not what was merely uploaded.
        "chars": sum(r["chars"] for r in succeeded),
        "ingested": results,
        "skipped": failures,
    }


@app.get("/api/brains/{name}/events")
async def brain_events(name: str, timeout_s: int = 600):
    """Stream ingestion progress as newline-delimited JSON.

    Deliberately the same streaming shape /api/ask already proved, rather than
    introducing SSE as a second way to stream. The user watches real pipeline
    states, so a slow ingest looks like work rather than a hang.
    """
    if memory_layer.PROVIDER != "cloud":
        raise HTTPException(status_code=400, detail="Progress needs PROVIDER=cloud.")

    import cognee_cloud

    async def gen():
        deadline = time.time() + timeout_s
        last = None
        while time.time() < deadline:
            try:
                state = await asyncio.to_thread(cognee_cloud.status, name)
            except Exception as exc:  # noqa: BLE001
                yield json.dumps({"stage": "error", "message": str(exc)[:300]}) + "\n"
                return

            blob = json.dumps(state)
            if blob != last:
                last = blob
                yield json.dumps(
                    {"stage": "poll", "state": _pipeline_state(state), "status": state}
                ) + "\n"

            # Distinguish the two terminal outcomes. Previously ANY terminal
            # state emitted "ready", so an ingestion that failed server-side was
            # reported to the user as a finished, working brain.
            kind = cognee_cloud.terminal_kind(state)
            if kind == "success":
                yield json.dumps({"stage": "ready"}) + "\n"
                return
            if kind == "failure":
                yield json.dumps(
                    {
                        "stage": "failed",
                        "state": _pipeline_state(state),
                        "detail": _failure_detail(state),
                    }
                ) + "\n"
                return

            await asyncio.sleep(3)

        yield json.dumps({"stage": "timeout"}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.delete("/api/brains/{name}")
def delete_brain(name: str):
    """Remove a brain.

    RESERVED_NAMES is enforced here as well as in create_brain. The UI hides the
    delete button for the demo and system brains, but the API is the real
    boundary — and `DELETE /api/brains/default_dataset` would otherwise delete
    Cognee's own internal dataset. The demo guard also lives inside
    cognee_cloud.delete_dataset, so neither layer can be bypassed on its own.
    """
    if memory_layer.PROVIDER != "cloud":
        raise HTTPException(status_code=400, detail="Deletion needs PROVIDER=cloud.")

    # Normalise first, so a case trick such as "Company_Brain" cannot slip past
    # the reserved check and then match an existing dataset.
    safe = normalize_brain_name(name)
    if safe and safe in RESERVED_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"'{safe}' is reserved and cannot be deleted.",
        )

    try:
        import cognee_cloud

        removed = cognee_cloud.delete_dataset(safe or name)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)[:300]) from exc
    if not removed:
        raise HTTPException(status_code=404, detail=f"No brain called '{name}'.")
    return {"ok": True, "deleted": safe or name}


# --------------------------------------------------------------------------
# reading a source document back
# --------------------------------------------------------------------------

@app.get("/api/source")
def source(name: str, dataset: str | None = None):
    """Return the text of a cited source document, so a citation is checkable.

    A citation you cannot open is an assertion. This makes it verifiable.

    Path safety: only a bare filename is accepted - no separators, no parent
    references - and the resolved path is re-checked to be inside corpus/
    before it is read. `basename` alone is not enough on its own, so both
    checks run.
    """
    import re as _re

    if not name or not _re.fullmatch(r"[A-Za-z0-9._ -]{1,120}", name):
        raise HTTPException(status_code=400, detail="Invalid source name.")
    if os.path.basename(name) != name:
        raise HTTPException(status_code=400, detail="Invalid source name.")

    # 1. the corpus on disk (the demo brain, and anything committed)
    corpus_root = os.path.realpath(os.path.join(HERE, "corpus"))
    path = os.path.realpath(os.path.join(corpus_root, name))
    if path.startswith(corpus_root + os.sep) and os.path.isfile(path):
        with open(path, encoding="utf-8", errors="replace") as fh:
            return {"ok": True, "name": name, "source": "corpus", "text": fh.read()}

    # 2. an uploaded document, read back from the tenant.
    #
    # Skipped for the demo brain: its corpus is on disk, so a miss there is a
    # genuine 404. Without this guard an unknown name fell through to the tenant,
    # which resolves the whole dataset map first and took ~20s to say "not found".
    target = dataset or DEMO_DATASET
    if target == DEMO_DATASET:
        raise HTTPException(status_code=404, detail=f"No source document called '{name}'.")

    try:
        import citations
        import cognee_cloud

        data_id = citations.data_id_for(target, name)
        if data_id:
            text = cognee_cloud.data_raw(cognee_cloud.resolve_id(target), data_id)
            return {"ok": True, "name": name, "source": "tenant", "text": text}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:200]) from exc

    raise HTTPException(status_code=404, detail=f"No source document called '{name}'.")


# --------------------------------------------------------------------------
# pages
# --------------------------------------------------------------------------

def _page(filename: str) -> FileResponse:
    """Serve a page with revalidation forced.

    These are hand-edited files with no build step and no content hash, so a
    browser that caches them will happily keep serving a version from before the
    last change — which looks exactly like "the feature was never built". Making
    the browser revalidate costs one conditional request and removes that whole
    class of confusion.
    """
    return FileResponse(
        os.path.join(HERE, "static", filename),
        headers={
            "Cache-Control": "no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@app.get("/")
def index():
    return _page("index.html")


@app.get("/graph")
def graph_page():
    return _page("graph.html")


@app.get("/brains")
def brains_page():
    return _page("brains.html")


@app.get("/upload")
def upload_page():
    return _page("upload.html")


if __name__ == "__main__":
    import uvicorn

    # Render injects PORT and requires binding to 0.0.0.0. Locally we want
    # 127.0.0.1. Same file works in both places with these two defaults.
    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )
