"""Web tier: serves the UI and streams answers.

WHY THIS FILE EXISTS SEPARATELY FROM pipeline.py
Render task runs cannot accept inbound connections (no ports), so the workflow
service can never serve the UI. Two services are therefore mandatory:

  this web tier  ->  Cognee Cloud tenant      (serves HTTP, answers questions)
  pipeline.py    ->  Cognee Cloud tenant      (fans ingestion across containers)

WHAT IS *NOT* TRUE, stated plainly because an earlier draft of this docstring
claimed it: the web tier does NOT trigger Render Workflow runs. `POST /api/brains`
ingests by calling memory_layer -> cognee_cloud directly, so uploads get no
retry and no fan-out from the workflow tier. pipeline.py is the parallel-ingest
path used by ingest.py, and it is the path that scales. Routing uploads through
it is the obvious next step, not something this file already does.

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
import threading
import time
import urllib.parse
from pathlib import Path

# --- environment must load BEFORE memory_layer is imported ---------------
# memory_layer reads PROVIDER at import time, so a .env loaded afterwards
# would silently be ignored and the app would fall back to the mock provider.
HERE = os.path.dirname(os.path.abspath(__file__))

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(HERE, ".env"))
    # the summarizer uses the platform LLM key (same key as the local brain)
    load_dotenv(os.path.join(HERE, ".env.oss"))
except ImportError:  # dotenv is optional; env vars still work
    pass

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.responses import FileResponse, RedirectResponse  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

import auth  # noqa: E402
import documents  # noqa: E402
import agents  # P6 agent layer
import observe  # P5 observability (fail-open)

import ocr  # noqa: F401  (stage-2 attachment OCR)
import memory_layer  # noqa: E402
import storage  # noqa: E402
from memory_layer import recall  # noqa: E402
from summarizer import summarize_history  # noqa: E402

app = FastAPI(title="Kestrel Company Brain")


# S9: response hardening. No CSP — the pages run inline scripts throughout,
# blocking CSP would white-screen the product; the safe headers (framing,
# sniffing, referrer) cost nothing. HSTS is intentionally absent: this tier
# also serves plain-HTTP localhost, where it would do harm.
@app.middleware("http")
async def _security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


# S5: per-identity cost guard. llm_calls metering can count spend, but nothing
# STOPPED spend: any valid identity could stream asks (each a hedged LLM
# recall), 5MB x 40 uploads, or 900s event polls without bound. Token-bucket
# per key, process-local (single-worker tier; a multi-worker deploy needs a
# shared bucket — flagged for P4). Generous defaults; env overrides; the
# battery (AUTH_MODE=off, local caller) never trips them.
_RATE_BUCKETS: dict = {}
_RATE_LOCK = threading.Lock()


def _rate_limit(key: str, capacity: int, per_seconds: int) -> bool:
    """True when the call may proceed (token consumed); False when limited."""
    now = time.time()
    with _RATE_LOCK:
        tokens, stamp = _RATE_BUCKETS.get(key, (float(capacity), now))
        tokens = min(float(capacity), tokens + (now - stamp) * capacity / per_seconds)
        if tokens < 1.0:
            _RATE_BUCKETS[key] = (tokens, now)
            return False
        _RATE_BUCKETS[key] = (tokens - 1.0, now)
        return True


def _caller_key(request: Request) -> str:
    ident = getattr(request.state, "identity", None) or {}
    client = getattr(request, "client", None)
    return str(ident.get("user_id") or ident.get("org_id")
               or request.headers.get("authorization", "")[:32]
               or (client.host if client else "local"))


def _check_rate(request: Request, scope: str) -> None:
    defaults = {"ask": 60, "upload": 20, "events": 30}
    cap = int(os.getenv(f"RATE_{scope.upper()}_PER_MIN",
                        str(defaults.get(scope, 60))))
    if not _rate_limit(f"{scope}:{_caller_key(request)}", cap, 60):
        raise HTTPException(status_code=429,
                            detail="Rate limit exceeded — slow down and retry.")

# One shared stylesheet and sidebar for every page. Serving them from /static
# means the shell is written once instead of pasted into four HTML files.
class NoCacheStaticFiles(StaticFiles):
    """Static assets that the browser may not cache stale.

    Without a Cache-Control header, browsers heuristic-cache these files —
    which is exactly how a redesigned shell.css kept appearing as the OLD
    dark theme (the HTML revalidated, the stylesheet didn't). These are
    hand-edited files with no content hash, so revalidate always.
    """

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


app.mount("/static", NoCacheStaticFiles(directory=os.path.join(HERE, "static")), name="static")

# --------------------------------------------------------------------------
# The React frontend (docs/FRONTEND_FIX_PLAN.md Phase A)
# --------------------------------------------------------------------------
# frontend/ is a Vite + React app that renders the same DOM the legacy shell
# did, styled by the legacy stylesheets. It is a built artifact (frontend/dist,
# committed — the app tier has no Node), and it is served from the ORIGIN ROOT
# because its index.html references /assets/... absolutely and it has no path
# routes: every deep link is a query param on / (?brain= ?chat= ?view= ?new=).
#
# KESTREL_UI selects which UI a browser gets at "/":
#   react  — frontend/dist/index.html (with /assets, /favicon.svg)
#   legacy — static/index.html, the pre-port dashboard
# Default flipped to react on 2026-10-03 after the Phase A/B gates passed:
# tests/test_react_clerk.py proves the served bundle is authenticated in clerk
# mode (with a no-token control run) and that asks stream, carry conversation
# context and report failures honestly. Setting KESTREL_UI=legacy is the
# rollback, and the legacy pages stay reachable either way.
DIST_DIR = os.path.join(HERE, "frontend", "dist")
UI_MODE = (os.getenv("KESTREL_UI") or "react").strip().lower()
if UI_MODE not in ("react", "legacy"):
    # A typo must not silently pick a UI the operator did not ask for.
    raise SystemExit(f"KESTREL_UI={UI_MODE!r} is not one of: react, legacy")


def _dist_file(name: str) -> str:
    return os.path.join(DIST_DIR, name)


def react_available() -> bool:
    return os.path.isfile(_dist_file("index.html"))


class ImmutableStaticFiles(StaticFiles):
    """Content-hashed build assets (index-CAqIOa5l.js): cache them forever.

    The opposite policy to NoCacheStaticFiles above, and for the same reason:
    those files have no content hash and heuristically cache stale; these have
    a hash in the name, so a new build is a new URL and the old one can never
    be served by mistake. Without an explicit header, browsers revalidate every
    asset on every load.
    """

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


# Mount only dist/assets — never frontend/ itself, which would publish src/,
# package.json and node_modules. Skipped (with a loud line) when the bundle is
# absent so the legacy UI still boots from a source-only checkout.
if os.path.isdir(os.path.join(DIST_DIR, "assets")):
    app.mount(
        "/assets",
        ImmutableStaticFiles(directory=os.path.join(DIST_DIR, "assets")),
        name="app-assets",
    )

storage.init()   # Postgres persistence (P2): degrades to unavailable
try:
    import connectors
    connectors.init_vault()   # P6: OAuth credential vault (no-op without CONNECTOR_VAULT_KEY)
    connectors.init_slack_workspaces()   # P6: per-workspace Slack grants
except Exception:
    pass

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
# (RESERVED_NAMES lives below normalize_brain_name — it holds normalized names.)

# H5: request-size limits. The honest client sends ~1 question and 3 turns of
# context, so these are generous - they exist to bound the API, not the user.
MAX_QUESTION_CHARS = 2_000
MAX_CONTEXT_CHARS = 6_000


# --------------------------------------------------------------------------
# tenant resolution and dataset authorisation
# --------------------------------------------------------------------------
# Backward compatible: when no tenants are configured every caller resolves to
# one unrestricted tenant, which is exactly the previous behaviour. Enforcement
# begins the moment fixtures/tenants.json exists.

def current_tenant(request: Request):
    """Resolve the caller from the X-API-Key header."""
    import tenants

    return tenants.resolve(request.headers.get("x-api-key"))


def require_tenant(request: Request):
    """P3 identity gate. AUTH_MODE=off → single local user (as before).
    AUTH_MODE=clerk → a valid Clerk session JWT is required; the identity is
    stored on the request state for the brain-authorization check. The legacy
    X-API-Key tenants gate still applies when Clerk is off and tenants are
    configured."""
    if auth.active():
        identity = auth.identity_from_request(request.headers.get("authorization"))
        if identity is None:
            raise HTTPException(
                status_code=401,
                detail="A valid Clerk session token is required.",
            )
        request.state.identity = identity
        return identity

    import tenants

    if not tenants.configured():
        return None                       # single-tenant mode: unchanged
    tenant = tenants.resolve(request.headers.get("x-api-key"))
    if tenant is None:
        raise HTTPException(
            status_code=401,
            detail="A valid X-API-Key header is required.",
        )
    return tenant


def brain_allowed(request: Request, brain: str) -> None:
    """P3 brain authorization: shared brains readable by every authenticated
    identity; user-created brains only by their org, or by the creator when
    org-less (SEC-8). No-op when auth is off.

    SEC-2: fail CLOSED. An unknown brain (no row — script-ingested, pre-P3,
    ops-created) is 403, not allowed — and per owner decision the demo has
    NO blanket allow either: company_brain carries a real ownership row
    (creator-owned), so every brain answers to the same rule, including
    during a Postgres outage (lookup failure lands here as None → 403)."""
    if not auth.active():
        return
    identity = getattr(request.state, "identity", None) or {}
    org = identity.get("org_id")
    rec = storage.brain_access(brain)
    if rec is None:
        raise HTTPException(status_code=403, detail="Unknown brain.")
    if rec.get("is_shared"):
        return
    if rec.get("org_id") and rec.get("org_id") == org:
        return
    if rec.get("created_by") and rec.get("created_by") == identity.get("user_id"):
        return
    raise HTTPException(status_code=403,
                        detail="This brain belongs to another workspace.")


def require_dataset_access(request: Request, dataset: str | None) -> None:
    """403 unless the caller's tenant may reach `dataset`.

    Every read route funnels through here rather than checking inline, so a new
    route cannot forget the check by omission - it has to actively skip a call.
    """
    # P3: the Clerk identity gate FIRST — the legacy tenants early-return
    # used to bypass it entirely (an unauthenticated ask returned 200).
    identity = require_tenant(request)
    if not auth.active():
        import tenants

        if not tenants.configured():
            return
        if not identity.allows(dataset):
            raise HTTPException(
                status_code=403,
                detail=f"'{dataset}' is not available to this account.",
            )
    brain_allowed(request, dataset or DEMO_DATASET)
    return identity


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


# The UI's display key for the demo brain. Every localStorage namespace,
# sidebar folder, and default brain param uses "demo" while the dataset is
# company_brain (DEMO_DATASET) — resolve the alias at the same edge, or
# fail-closed authz 403s the entire demo surface (no "demo" ownership row
# can ever exist).
DEMO_ALIAS = "demo"


def safe_dataset(raw: str | None) -> str:
    """One name, one meaning, at every route edge (SEC-1/NEW-1).

    Authz looks rows up exactly and rows are stored normalized, so every
    handler must authorize the NORMALIZED name and then use that same name
    downstream. Unnormalizable input falls back to the demo dataset — the
    same default the routes already used for a missing name.
    """
    norm = normalize_brain_name(raw or "")
    if norm == DEMO_ALIAS:
        return DEMO_DATASET
    return norm or DEMO_DATASET


# S8: compared against NORMALIZED names — so the set holds normalized names.
# A raw COGNEE_DATASET like "Acme-Demo" would otherwise leave its normalized
# twin ("acme_demo") creatable/deletable past this guard.
RESERVED_NAMES = {normalize_brain_name(DEMO_DATASET) or DEMO_DATASET,
                  "default_dataset", "company_brain"}


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
    # SEC-6: normalize at the edge (a traversal maps to a plain wrong-brain
    # name, never a path) and confine every candidate inside BRAINS_DIR.
    target = safe_dataset(dataset)
    cloud_error = None

    try:
        import cognee_cloud

        return cognee_cloud.graph(target), "cloud"
    except Exception as exc:  # noqa: BLE001
        cloud_error = str(exc)[:200]

    base = BRAINS_DIR.resolve()
    legacy = Path(GRAPH_FIXTURE).resolve()
    candidates = []
    for cand in [BRAINS_DIR / f"{target}.json"] + (
            [GRAPH_FIXTURE] if target == DEMO_DATASET else []):
        try:
            resolved = cand.resolve()
        except Exception:  # noqa: BLE001 - unresolvable path: skip it
            continue
        # Confined to BRAINS_DIR — except the legacy single-brain snapshot,
        # which lives one level up by design and is allow-listed exactly.
        if resolved.parent != base and resolved != legacy:
            continue
        candidates.append(cand)

    for path in candidates:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            continue
        except Exception as exc:  # noqa: BLE001
            cloud_error = f"{cloud_error}; {path.name}: {exc}"[:300]
            continue
        # S10: snapshots are committed JSON (and tenant payloads pass through
        # here too) — validate shape and size before serving to every reader.
        # A truncated export or a compromised payload otherwise 500s/OOMs here.
        try:
            nodes, edges = data.get("nodes"), data.get("edges")
            if not isinstance(nodes, list) or not isinstance(edges, list):
                raise ValueError("snapshot must hold nodes[]/edges[]")
            if len(nodes) > 100_000 or len(edges) > 500_000:
                raise ValueError("snapshot exceeds sane bounds")
            return data, "fixture"
        except Exception as exc:  # noqa: BLE001
            cloud_error = f"{cloud_error}; {path.name}: bad snapshot ({exc})"[:300]
            continue

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
    import llm as _llm
    payload = {
        "ok": True,
        "provider": memory_layer.PROVIDER,
        "dataset": DEMO_DATASET,
        # Phase: guarded provider switch — inspectable route/probe state
        "llm": {
            "route": os.getenv("KESTREL_LLM_ROUTE", "auto"),
            "active_base": (_llm.base_url() or "").split("//")[-1].split(".")[0],
            "active_model": _llm.default_model(),
            "nova_status": _llm.nova_probe_status(),
        },
        # LOW-5: /health is unauthenticated — it reports status booleans, not
        # infrastructure coordinates (no service URL, no DB host).
        "storage": {"storage": storage.status().get("storage")},
    }
    # T4: `provider` names the CLASS of backend ("cloud" = a Cognee API
    # server, vs mock) — the footer read it as the hosted tenant even when it
    # is the local OSS container. Report a coarse location instead: no host,
    # no URL, just which kind of brain this is.
    try:
        import cognee_cloud
        from urllib.parse import urlparse

        _host = urlparse(cognee_cloud._base() or "").hostname or ""
    except Exception:  # noqa: BLE001 - a label must never break the probe
        _host = ""
    payload["backend"] = (
        "local oss" if _host in ("localhost", "127.0.0.1", "::1") else "cloud tenant"
    )
    # O4: prove the tenant reachable, but NEVER hang the liveness probe on
    # it — two synchronous tenant calls here once turned tenant slowness
    # into web-tier restart loops. Cached 30s, refresh failures keep stale.
    if payload["provider"] == "cloud":
        payload.update(_upstream_cached())
    return payload


_UPSTREAM_CACHE: dict = {"at": 0.0, "payload": {"upstream": "unknown"}}
_UPSTREAM_TTL = 30.0


def _upstream_cached() -> dict:
    now = time.time()
    if now - _UPSTREAM_CACHE["at"] < _UPSTREAM_TTL:
        return dict(_UPSTREAM_CACHE["payload"])
    # Prove the tenant instance is actually reachable, not just configured.
    fresh: dict = {}
    try:
        import cognee_cloud

        upstream = cognee_cloud.health()
        fresh["upstream"] = upstream.get("status", "unknown")
        fresh["components"] = {
            k: v.get("status") for k, v in (upstream.get("components") or {}).items()
        }

        # The tenant's /health endpoint is UNAUTHENTICATED. It therefore
        # reports "healthy" even when our API key is wrong — we verified
        # this by pointing the app at a bad key and watching /health claim
        # everything was fine while every query returned 401. So probe an
        # authenticated endpoint too, or this check is worse than useless.
        try:
            cognee_cloud.datasets()
            fresh["auth"] = "ok"
        except Exception as exc:  # noqa: BLE001
            fresh["auth"] = "failed"
            fresh["auth_error"] = str(exc)[:160]
    except Exception as exc:  # noqa: BLE001 - health must never raise
        # Refresh failed: keep serving the last good reading (or "unknown"
        # on first boot) rather than hanging the probe on a sick tenant.
        if _UPSTREAM_CACHE["payload"].get("upstream") == "unknown":
            fresh = {"upstream": "unreachable", "upstream_error": str(exc)[:200]}
        else:
            return dict(_UPSTREAM_CACHE["payload"])
    _UPSTREAM_CACHE["at"] = now
    _UPSTREAM_CACHE["payload"] = fresh
    return dict(fresh)


# --------------------------------------------------------------------------
# read path — every route accepts an optional dataset
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# server-side chat persistence (P2) — Postgres is the source of truth when
# available; the UI keeps localStorage as its offline fallback
# --------------------------------------------------------------------------

@app.get("/api/config")
def config():
    return {
        "authMode": auth.mode(),
        "publishableKey": os.getenv("CLERK_PUBLISHABLE_KEY", "") if auth.active() else "",
        # CH-1: the turn cap the client must respect. Published from here so the
        # number the server rejects and the number the client trims to cannot
        # drift into two different literals.
        "maxTurns": storage.MAX_TURNS,
    }


@app.post("/api/chats")
async def chats_upsert(request: Request):
    identity = require_tenant(request)
    # LOW-6: malformed JSON must be 400, not 500.
    try:
        record = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Request body must be JSON.")
    if not isinstance(record, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object.")
    if not record.get("id"):
        raise HTTPException(status_code=422, detail="chat id required")
    if not storage.available():
        raise HTTPException(status_code=503, detail="storage unavailable")
    # SEC-5/NEW-4: stamp ownership + brain server-side; the record's own
    # org_id is ignored (storage.upsert_chat takes the stamped values).
    org = identity.get("org_id") if isinstance(identity, dict) else None
    uid = identity.get("user_id") if isinstance(identity, dict) else None
    brain = safe_dataset(request.query_params.get("brain") or record.get("brain"))
    # CH-6: filing a chat under a brain IS a brain access. Every other write
    # route gates on the dataset; this one only stamped it, so a tenant could
    # park its conversations inside another tenant's brain (they would not be
    # listed there, but the ownership record would be wrong from then on).
    require_dataset_access(request, brain)
    # O6: bound the write — an unbounded turns array holds one transaction
    # inserting thousands of rows and every restore re-reads it all.
    turns = record.get("turns") or []
    if not isinstance(turns, list):
        raise HTTPException(status_code=422, detail="turns must be a list")
    if len(turns) > storage.MAX_TURNS:
        raise HTTPException(status_code=413,
                            detail=f"Too many turns in one chat ({storage.MAX_TURNS} max).")
    for t in turns:
        if not isinstance(t, dict):
            raise HTTPException(status_code=422, detail="each turn must be an object")
    # CH-9: only `text` used to be capped, and the storage layer crashed on a
    # non-numeric workedMs — an unbounded `steps` array or a string field turned
    # a save into a 500. Bound the rest of the payload the same way.
    if any(len(t.get("text") or "") > 100_000 for t in turns):
        raise HTTPException(status_code=413, detail="Turn text too large.")
    if any(len(json.dumps(t.get(k) or [])) > 500_000
           for t in turns for k in ("sources", "attachments", "steps")):
        raise HTTPException(status_code=413, detail="Turn metadata too large.")
    try:
        return storage.upsert_chat(record, org=org, brain=brain, created_by=uid)
    except storage.OwnershipError:
        # S1: somebody else's chat id — indistinguishable from missing.
        raise HTTPException(status_code=404, detail="Chat not found.")
    except storage.TruncationError as exc:
        # CH-1: the client sent fewer turns than we hold. Say so loudly instead
        # of deleting history in silence; the client retries with trim=true if
        # it really means it.
        raise HTTPException(
            status_code=409,
            detail=(f"This save carries {exc.incoming} turns but {exc.stored} are "
                    "stored — refusing to delete history. Send trim=true to "
                    "overwrite deliberately."),
        )
    except storage.ResurrectError:
        # CH-2: 410 Gone, not 409 — this resource is permanently gone, and the
        # client must not fight it. A stale tab (or another device) holding a
        # deleted id used to re-create the chat the user threw away; now it is
        # told to move on, and the React client re-saves under a fresh id so the
        # conversation the user is still reading is not lost either.
        raise HTTPException(status_code=410,
                            detail="This chat was deleted. Start a new chat.")
    except storage.db_error as exc:
        # CH-8: a mid-life storage failure is a 503, not a stack-traced 500.
        storage.mark_down(f"chats_upsert: {exc}")
        raise HTTPException(status_code=503, detail="storage unavailable")


@app.get("/api/chats")
def chats_list(request: Request, brain: str | None = None, limit: int = 200):
    identity = require_tenant(request)
    if not storage.available():
        return {"ok": False, "chats": [], "storage": _public_storage()}
    # NEW-3: a client-supplied brain filter is a brain access — gate it.
    if brain:
        brain = safe_dataset(brain)
        require_dataset_access(request, brain)
    org = identity.get("org_id") if isinstance(identity, dict) else None
    uid = identity.get("user_id") if isinstance(identity, dict) else None
    limit = min(max(int(limit or 200), 1), 500)
    try:
        chats = storage.list_chats(brain, org=org, user_id=uid, limit=limit)
        # CH-7: `total` was promised by the comment below and never delivered,
        # so a capped page was indistinguishable from the whole history.
        total = storage.count_chats(brain, org=org, user_id=uid)
    except storage.db_error as exc:
        storage.mark_down(f"chats_list: {exc}")
        raise HTTPException(status_code=503, detail="storage unavailable")
    return {"ok": True, "chats": chats, "returned": len(chats),
            "total": total, "truncated": total > len(chats), "limit": limit}


def _public_storage() -> dict:
    """S6: storage.status() carries the DB host + driver errors — fine for
    logs, not for API responses. Callers get the status boolean only."""
    return {"storage": storage.status().get("storage")}


@app.get("/api/chats/{chat_id}")
def chats_get(request: Request, chat_id: str):
    identity = require_tenant(request)
    if not storage.available():
        raise HTTPException(status_code=503, detail="storage unavailable")
    # LOW-11: identity is not ownership — scope the read; 404 (not 403) so a
    # foreign id is indistinguishable from a missing one.
    org = identity.get("org_id") if isinstance(identity, dict) else None
    uid = identity.get("user_id") if isinstance(identity, dict) else None
    try:
        chat = storage.get_chat(chat_id, org=org, user_id=uid) if auth.active() \
            else storage.get_chat(chat_id)
    except storage.db_error as exc:
        storage.mark_down(f"chats_get: {exc}")
        raise HTTPException(status_code=503, detail="storage unavailable")
    if chat is None:
        # 404, not 200-with-null: the client could not tell "this chat does not
        # exist" from "this chat is empty", so clicking a stale sidebar row (a
        # deleted chat, one deleted in another tab, or someone else's) did
        # nothing at all — no navigation, no error. DELETE already treats a
        # foreign/missing id as 404 ("indistinguishable from missing"); the read
        # now matches it. The legacy shell's restore treats !ok and a null chat
        # identically (it falls through to localStorage), so this is safe for it
        # too.
        raise HTTPException(status_code=404, detail="No such chat.")
    return {"chat": chat}


@app.delete("/api/chats/{chat_id}")
def chats_delete(request: Request, chat_id: str):
    identity = require_tenant(request)
    if not storage.available():
        raise HTTPException(status_code=503, detail="storage unavailable")
    # SEC-4: identity is not ownership — stamped rows need an org match.
    # 404 either way: foreign ids are indistinguishable from missing ones.
    org = identity.get("org_id") if isinstance(identity, dict) else None
    uid = identity.get("user_id") if isinstance(identity, dict) else None
    try:
        deleted = storage.delete_chat(chat_id, org=org, user_id=uid) \
            if auth.active() else storage.delete_chat(chat_id)
    except storage.db_error as exc:
        storage.mark_down(f"chats_delete: {exc}")
        raise HTTPException(status_code=503, detail="storage unavailable")
    if not deleted:
        # CH-3: this used to answer 200 {"ok": false} while the comment above
        # promised a 404. A UI that only checks the status line toasted
        # "Chat deleted" for a delete that removed nothing — and the chat came
        # back on the next list. Zero rows is now the 404 the route claimed.
        raise HTTPException(status_code=404, detail="No such chat for this account.")
    return {"ok": True, "id": chat_id}


@app.get("/api/usage")
def usage(request: Request, days: int = 30):
    identity = require_tenant(request)
    days = max(1, min(days, 365))
    if not storage.available():
        return {"ok": False, "usage": []}
    # LOW-4: scope metering to the caller's org; auth-off keeps the old
    # platform-wide view.
    org = identity.get("org_id") if isinstance(identity, dict) else None
    uid = identity.get("user_id") if isinstance(identity, dict) else None
    rows = storage.usage_summary(days, org=org, user_id=uid) if auth.active() \
        else storage.usage_summary(days)
    return {"ok": True, "usage": rows}


@app.post("/api/summarize")
async def summarize(request: Request):
    """Rolling-history summarization (P2): older turns compressed into a
    stable summary so multi-turn context stays bounded and cache-friendly."""
    require_tenant(request)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - malformed JSON is 400, not 500
        raise HTTPException(status_code=400, detail="Request body must be JSON.")
    older = body.get("older") or []
    if not older:
        return {"summary": ""}
    texts = [f"{t.get('role','user')}: {t.get('text','')}" for t in older]
    joined = "\n".join(texts)[-12000:]
    summary = await summarize_history(joined)
    return {"summary": summary}


@app.post("/api/extract")
async def extract_attachment(request: Request):
    """Extract text from ONE chat attachment so the CURRENT answer can use it.

    The ask path feeds text-like files client-side, but PDFs and DOCX keep
    their text in binary — pypdf/python-docx extraction has to happen here.
    This returns the text and touches nothing else: brain ingest remains the
    separate, explicit upload that makes the file answerable in FUTURE asks.
    """
    require_tenant(request)
    _check_rate(request, "upload")
    form = await request.form()
    upload = form.get("file")
    if upload is None or isinstance(upload, str):
        raise HTTPException(status_code=400, detail="Attach one file as 'file'.")
    data = await upload.read()
    name = upload.filename or "attachment"
    ocr_used = False
    try:
        text = documents.extract(name, data)
    except documents.ExtractError as exc:
        # Stage 2: scanned pages carry no text layer — read them with the
        # vision model before giving up (PDF only; DOCX is always layered).
        ocr_fallback = (
            isinstance(exc, documents.ExtractEmpty)
            and name.lower().endswith(".pdf")
            and ocr.available()
        )
        if not ocr_fallback:
            raise HTTPException(status_code=400, detail=str(exc))
        try:
            # COR-11 class: read_pdf blocks (requests) — run it in a worker
            # thread or it freezes the ENTIRE event loop for every caller
            text, _model = await asyncio.to_thread(ocr.read_pdf, data)
            ocr_used = True
        except RuntimeError as ocr_exc:
            raise HTTPException(status_code=400, detail=str(ocr_exc))
    except Exception as exc:  # noqa: BLE001 - any parse failure is a 400
        raise HTTPException(
            status_code=400, detail=f"Could not read this file: {exc}"
        ) from exc
    return {"ok": True, "name": name, "chars": len(text),
            "text": text, "ocr": ocr_used}


@app.post("/api/actions/draft")
async def actions_draft(request: Request):
    """P6: turn an answered question into a DRAFT email or Slack message.

    The agent only drafts — nothing here sends. Pydantic AI gives typed
    outputs (to/subject/body or channel/text) so the UI renders real fields.
    """
    identity = require_tenant(request)
    _check_rate(request, "ask")
    body = await request.json()
    kind = (body.get("kind") or "email").lower()
    question = (body.get("question") or "")[:2000]
    answer = (body.get("answer") or "")[:12000]
    sources = [s for s in (body.get("sources") or []) if isinstance(s, str)][:20]
    instructions = (body.get("instructions") or "")[:1000]
    if not answer:
        raise HTTPException(status_code=400, detail="No answer text to draft from.")
    try:
        if kind == "email":
            draft = await agents.draft_email(
                question, answer, sources, instructions,
                recipient=body.get("recipient"))
            payload = draft.model_dump()
        elif kind == "message":
            draft = await agents.draft_message(
                question, answer, sources, instructions,
                channel_hint=body.get("channel") or "")
            payload = draft.model_dump()
        else:
            raise HTTPException(status_code=400, detail="Unknown draft kind.")
    except Exception as exc:  # noqa: BLE001 - agent failures are surfaced, not fatal
        raise HTTPException(status_code=502, detail=f"Draft agent failed: {str(exc)[:200]}")
    observe.trace(feature=f"draft-{kind}", model=agents._model(),
                  user=(identity or {}).get("user_id"), brain=body.get("brain"),
                  ok=True, meta={"sources": len(sources)})
    return {"ok": True, "kind": kind, "draft": payload}


@app.post("/api/actions/send")
async def actions_send(request: Request):
    """P6: the APPROVAL GATE. Sends an explicitly reviewed draft through the
    configured transport. Unconfigured transports are a clean 503, and the
    send is traced (who sent what, where)."""
    identity = require_tenant(request)
    body = await request.json()
    kind = (body.get("kind") or "").lower()
    draft = body.get("draft") or {}
    try:
        if kind == "email":
            if not agents.email_configured():
                raise HTTPException(status_code=503, detail=(
                    "Email sending is not configured on this instance "
                    "(SMTP_HOST/SMTP_USER/SMTP_PASS required)."))
            d = agents.EmailDraft(**draft)
            result = await asyncio.to_thread(agents.send_email, d)
        elif kind == "slack":
            if not agents.slack_configured():
                raise HTTPException(status_code=503, detail=(
                    "Slack sending is not configured on this instance "
                    "(SLACK_WEBHOOK_URL required)."))
            d = agents.MessageDraft(**draft)
            result = await asyncio.to_thread(agents.send_slack, d)
        else:
            raise HTTPException(status_code=400, detail="Unknown send kind.")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - transport errors surface cleanly
        raise HTTPException(status_code=502, detail=f"Send failed: {str(exc)[:200]}")
    observe.trace(feature=f"send-{kind}", model=None,
                  user=(identity or {}).get("user_id"), ok=result.get("sent", False),
                  meta={"to": result.get("to") or result.get("status")})
    return {"ok": True, "result": result}


@app.get("/api/connectors/status")
def connectors_status(request: Request):
    """Which connector transports are configured — the UI renders honest
    states instead of dead buttons. Vault rows win; legacy env tokens count
    as configured (dev/legacy path)."""
    require_tenant(request)
    identity = getattr(request.state, "identity", None)
    import connectors as _cx
    return {
        "email_send": agents.email_configured(),
        "slack_send": agents.slack_configured(),
        # Read transports are usable only in the `connected` state. A
        # needs_reconnect grant cannot serve an import — advertising it true
        # would send the user to a 503.
        "slack_read": _cx.connection_state(
            "slack", identity, os.getenv("SLACK_BOT_TOKEN")) == "connected",
        "gmail_read": _cx.connection_state(
            "google", identity, os.getenv("GMAIL_APP_PASSWORD")
            if os.getenv("GMAIL_USER") else "") == "connected",
        "oauth": {p: {"configured": _cx.provider_configured(p),
                       "state": _cx.connection_state(p, identity)}
                  for p in ("google", "slack")},
    }


@app.get("/api/connectors/slack/connect")
def slack_connect(request: Request, mode: str = "read_post", private: int = 0):
    """Scope-picker entry: the dialog's choices become the Slack scope set.
    Redirects to Slack's consent screen; identity + choices bind into state."""
    from fastapi.responses import RedirectResponse
    import connectors as _cx
    identity = require_tenant(request)
    if not _cx.vault_configured():
        raise HTTPException(status_code=503, detail=(
            "Connector vault has no key (CONNECTOR_VAULT_KEY)."))
    if not _cx.provider_configured("slack"):
        raise HTTPException(status_code=503, detail=(
            "Slack OAuth is not configured on this instance."))
    mode = mode if mode in ("read", "read_post") else "read_post"
    return RedirectResponse(
        _cx.slack_connect_url(identity, mode, bool(private)), status_code=302)


@app.get("/api/connectors/slack/workspaces")
def slack_workspaces_list(request: Request):
    """Connected workspaces + granted access level — no tokens, ever."""
    import connectors as _cx
    identity = require_tenant(request)
    return {"ok": True, "workspaces": _cx.slack_list_workspaces(identity)}


def _slack_ws(identity, team_id: str) -> dict:
    import connectors as _cx
    ws = _cx.slack_get_workspace(identity, team_id)
    if not ws or not ws.get("bot_token"):
        raise HTTPException(status_code=404,
                            detail="That Slack workspace is not connected (or was disconnected).")
    scopes = (ws.get("scopes") or "")
    if "invalid_auth" in scopes or "token_revoked" in scopes:
        raise HTTPException(status_code=403, detail=(
            "The saved Slack token was revoked — reconnect the workspace."))
    return ws


@app.get("/api/connectors/slack/{team_id}/channels")
def slack_channels_route(request: Request, team_id: str,
                         types: str = "public_channel,private_channel",
                         cursor: str = ""):
    """conversations.list — private channels appear only when the grant
    included groups:read (and only if the bot was invited)."""
    identity = require_tenant(request)
    ws = _slack_ws(identity, team_id)
    import connectors as _cx
    try:
        out = _cx.slack_channels(ws["bot_token"], types, cursor=cursor, limit=100)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, **out}


@app.get("/api/connectors/slack/{team_id}/messages")
def slack_messages_route(request: Request, team_id: str, channel: str,
                         limit: int = 50, cursor: str = ""):
    """conversations.history with cursor pagination. DM/MPIM channels
    require the USER token (bot tokens cannot read them)."""
    identity = require_tenant(request)
    ws = _slack_ws(identity, team_id)
    limit = max(1, min(limit, 200))
    token = ws["bot_token"]
    if channel.startswith("D") and ws.get("user_token"):
        token = ws["user_token"]   # DMs/MPIMs are user-token territory
    import connectors as _cx
    try:
        out = _cx.slack_history(token, channel, limit=limit, cursor=cursor)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "channel": channel, **out}


@app.post("/api/connectors/slack/{team_id}/post")
async def slack_post_route(request: Request, team_id: str):
    """chat.postMessage — refused 403 unless the grant actually included
    chat:write. The read-only access level can never post."""
    identity = require_tenant(request)
    _check_rate(request, "ask")
    ws = _slack_ws(identity, team_id)
    if "chat:write" not in (ws.get("scopes") or ""):
        raise HTTPException(status_code=403, detail=(
            "This workspace granted read-only access — posting requires "
            "reconnecting with 'Read and post messages'."))
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - LOW-6 class
        raise HTTPException(status_code=400, detail="Request body must be JSON.")
    channel = (body.get("channel") or "").strip()
    text = (body.get("text") or "").strip()
    if not channel or not text:
        raise HTTPException(status_code=400, detail="channel and text are required.")
    if len(text) > 4000:
        raise HTTPException(status_code=413, detail="Message text too long (4000 char max).")
    import connectors as _cx
    try:
        out = _cx.slack_post(ws["bot_token"], channel, text)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    observe.trace(feature="slack-post", model=None,
                  user=(request.state.identity or {}).get("user_id")
                  if hasattr(request.state, "identity") else None,
                  ok=True, meta={"channel": channel})
    return {"ok": True, **out}


@app.post("/api/connectors/slack/{team_id}/disconnect")
async def slack_disconnect_route(request: Request, team_id: str):
    """auth.revoke at Slack, then delete the stored workspace. The grant is
    gone from both sides after this."""
    identity = require_tenant(request)
    import connectors as _cx
    ws = _cx.slack_get_workspace(identity, team_id)
    revoked = False
    if ws and ws.get("bot_token"):
        import asyncio as _aio
        revoked = await _aio.to_thread(_cx.slack_revoke, ws["bot_token"])
    removed = _cx.slack_delete_workspace(identity, team_id)
    return {"ok": True, "revoked": revoked, "removed": removed}


@app.get("/api/connectors/oauth/{provider}/start")
def connectors_oauth_start(request: Request, provider: str):
    """302 the browser to the provider's consent screen. Identity is bound
    server-side into `state` — the token that comes back can only ever land
    on the identity that started the flow."""
    from fastapi.responses import RedirectResponse
    import connectors as _cx
    identity = require_tenant(request)
    if provider not in _cx.PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider.")
    if not _cx.vault_configured():
        raise HTTPException(status_code=503, detail=(
            "Connector vault has no key (CONNECTOR_VAULT_KEY)."))
    if not _cx.provider_configured(provider):
        raise HTTPException(status_code=503, detail=(
            f"{provider} OAuth is not configured on this instance."))
    return RedirectResponse(_cx.authorize_url(provider, identity),
                            status_code=302)


@app.get("/api/connectors/oauth/{provider}/callback")
def connectors_oauth_callback(request: Request, provider: str,
                              code: str | None = None, state: str | None = None,
                              error: str | None = None):
    """Provider redirects here. Validates state, exchanges the code, stores
    the encrypted grant, lands on /?connected=<provider> for the UI toast."""
    from fastapi.responses import RedirectResponse
    import connectors as _cx
    if error:
        return RedirectResponse(f"/?connect_error={urllib.parse.quote(error[:80])}",
                                status_code=302)
    if provider not in _cx.PROVIDERS or not code or not state:
        return RedirectResponse("/?connect_error=bad_callback", status_code=302)
    rec = _cx.pop_state_full(state, provider)
    if rec is None:
        return RedirectResponse("/?connect_error=bad_state", status_code=302)
    identity, extra = rec.get("identity") or {}, rec.get("extra") or {}
    try:
        tokens, scopes = _cx.exchange_code(provider, code)
        if provider == "slack" and extra.get("mode"):
            # scope-picker flow: one row per WORKSPACE, with the access
            # level the user chose in the dialog
            mode = extra.get("mode") or "read"
            _cx.slack_put_workspace(
                identity, tokens.get("team_id") or "unknown",
                tokens.get("team") or "", tokens, scopes,
                mode, bool(extra.get("private")),
                bot_user_id=tokens.get("bot_user_id", ""))
        _cx.put_credential(provider, identity, tokens, scopes=scopes)
    except Exception as exc:
        return RedirectResponse(
            "/?connect_error=" + urllib.parse.quote(str(exc)[:80]),
            status_code=302)
    return RedirectResponse(f"/?connected={provider}", status_code=302)


@app.post("/api/connectors/disconnect")
async def connectors_disconnect(request: Request):
    """Forget a grant (vault row deleted). Stops future syncs; already
    imported documents stay cited — disconnect is not un-ingest."""
    import connectors as _cx
    identity = require_tenant(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    provider = (body.get("provider") or "").lower()
    if provider not in _cx.PROVIDERS:
        raise HTTPException(status_code=400, detail="Unknown provider.")
    return {"ok": _cx.delete_credential(provider, identity)}


@app.post("/api/connectors/import")
async def connectors_import(request: Request):
    """P6 connector: pull EXTERNAL messages (Slack channel history, Gmail
    inbox) into a brain through the same ingest primitive as uploads —
    imported text becomes citable like any uploaded document. Env-gated:
    SLACK_BOT_TOKEN for Slack, GMAIL_USER/GMAIL_APP_PASSWORD for Gmail."""
    identity = require_tenant(request)
    _check_rate(request, "upload")
    body = await request.json()
    source = (body.get("source") or "").lower()
    brain = safe_dataset(body.get("brain"))
    if not brain:
        raise HTTPException(status_code=400, detail="A valid target brain is required.")
    require_dataset_access(request, brain)
    limit = max(1, min(int(body.get("limit") or 25), 100))
    docs: list[dict] = []

    if source == "slack":
        import connectors as _cx
        # Vault bot token first (per-user OAuth grant), legacy env token
        # second. Rotation surfaces as invalid_auth → flip to reconnect.
        token = _cx.slack_token(identity) or ""
        channel = body.get("channel") or ""
        if not token or not channel:
            raise HTTPException(status_code=503, detail=(
                "Slack import is not configured (connect Slack in Settings, "
                "or set SLACK_BOT_TOKEN + channel id)."))
        import requests as _rq
        hist = _rq.get("https://slack.com/api/conversations.history",
                       headers={"Authorization": f"Bearer {token}"},
                       params={"channel": channel, "limit": limit}, timeout=30).json()
        if hist.get("error") == "invalid_auth":
            _cx.mark_needs_reconnect("slack", identity)
        if not hist.get("ok"):
            raise HTTPException(status_code=400,
                                detail="Slack history failed: " + str(hist.get("error"))[:120])
        for msg in reversed(hist.get("messages") or []):
            txt = (msg.get("text") or "").strip()
            if txt:
                docs.append({"name": f"slack-{msg.get('ts', 'msg')}.txt", "text": txt})
    elif source == "gmail":
        import connectors as _cx
        # OAuth grant first (Gmail REST API, per-user), IMAP app-password
        # second (legacy env path). Either way the text lands identically.
        gtok = _cx.google_access_token(identity)
        if gtok:
            import requests as _grq
            try:
                lr = _grq.get(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                    headers={"Authorization": f"Bearer {gtok}"},
                    params={"maxResults": limit, "q": body.get("query") or ""},
                    timeout=30)
                if lr.status_code == 401:
                    _cx.mark_needs_reconnect("google", identity)
                    raise HTTPException(status_code=401, detail=(
                        "Gmail grant expired or revoked — reconnect Google in Settings."))
                lr.raise_for_status()
                msgs = lr.json().get("messages", [])
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=502, detail=(
                    f"Gmail list failed: {exc}")[:150])
            for m in reversed(msgs):
                try:
                    full = _grq.get(
                        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}",
                        headers={"Authorization": f"Bearer {gtok}"},
                        params={"format": "full"}, timeout=30).json()
                    heads = {h["name"].lower(): h["value"]
                             for h in full.get("payload", {}).get("headers", [])}
                    import base64 as _b64

                    def _walk(part):
                        if part.get("mimeType", "").startswith("text/plain") \
                                and part.get("body", {}).get("data"):
                            return _b64.urlsafe_b64decode(
                                part["body"]["data"]).decode("utf-8", "ignore")
                        for sub in part.get("parts", []):
                            found = _walk(sub)
                            if found:
                                return found
                        return ""

                    txt = _walk(full.get("payload", {}))
                    if txt.strip():
                        docs.append({
                            "name": f"gmail-{(heads.get('subject') or m['id'])[:60]}.txt",
                            "text": f"From: {heads.get('from', '')}\n"
                                    f"Subject: {heads.get('subject', '')}\n\n{txt}"})
                except Exception:
                    continue
            if not docs:
                return {"ok": True, "imported": 0, "brain": brain}
        else:
            user, pwd = os.getenv("GMAIL_USER", ""), os.getenv("GMAIL_APP_PASSWORD", "")
            if not user or not pwd:
                raise HTTPException(status_code=503, detail=(
                    "Gmail import is not configured (connect Google in Settings, "
                    "or set GMAIL_USER + GMAIL_APP_PASSWORD)."))
            import imaplib, email as _email
            from email.header import decode_header as _dh

            def _dec(v):
                parts = _dh(v or "")
                return "".join(p.decode(c or "utf-8") if isinstance(p, bytes) else p
                               for p, c in parts)

            imap = imaplib.IMAP4_SSL("imap.gmail.com")
            imap.login(user, pwd)
            imap.select("INBOX")
            _, ids = imap.search(None, "ALL")
            batch = ids[0].split()[-limit:]
            for mid in reversed(batch):
                _, data = imap.fetch(mid, "(RFC822)")
                msg = _email.message_from_bytes(data[0][1])
                body_text = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body_text = part.get_payload(decode=True).decode(
                                part.get_content_charset() or "utf-8", "ignore")
                            break
                else:
                    body_text = msg.get_payload(decode=True).decode(
                        msg.get_content_charset() or "utf-8", "ignore")
                if body_text.strip():
                    docs.append({"name": f"email-{_dec(msg.get('Subject'))[:60] or mid.decode()}.txt",
                                 "text": f"From: {_dec(msg.get('From'))}\nSubject: {_dec(msg.get('Subject'))}\n\n{body_text}"})
            imap.logout()
    else:
        raise HTTPException(status_code=400, detail="Unknown connector source.")

    if not docs:
        return {"ok": True, "imported": 0, "brain": brain}
    results = []
    for d in docs[:limit]:
        try:
            await memory_layer.remember(d["text"][:50000], brain, d["name"])
            results.append({"name": d["name"], "ok": True})
        except Exception as exc:  # noqa: BLE001 - report per-doc failures
            results.append({"name": d["name"], "ok": False, "error": str(exc)[:150]})
    imported = sum(1 for r in results if r["ok"])
    observe.trace(feature=f"import-{source}", brain=brain,
                  user=(identity or {}).get("user_id"),
                  ok=imported > 0, meta={"imported": imported})
    return {"ok": True, "imported": imported, "failed": len(results) - imported,
            "brain": brain, "docs": results}


@app.get("/api/ask")
async def ask(request: Request, q: str, dataset: str | None = None,
              context: str | None = None, tz: str | None = None,
              local_time: str | None = None):
    """Stream the answer as newline-delimited JSON so the UI never sits blank.

    `context` carries the preceding turns of the conversation. It is prepended
    to the question so a follow-up ("and who signs it off?") is resolved against
    what was already asked — without it, every turn is a cold start and a
    follow-up question has no referent.
    """
    # SEC-1/NEW-1: authorize the normalized name and use it everywhere
    # downstream — one name, one meaning, start to finish.
    dataset = safe_dataset(dataset)
    identity = require_dataset_access(request, dataset)
    # S5: asks cost inference — bound per caller (generous; see _check_rate).
    _check_rate(request, "ask")
    # straight into the prompt. Unbounded input is unbounded token cost on every
    # call - a trivial way to inflate the inference bill. Mirrors how
    # documents.py caps uploads: refuse early with a clear reason.
    if len(q) > MAX_QUESTION_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Question is too long ({len(q)} chars). The limit is {MAX_QUESTION_CHARS}.",
        )
    if context and len(context) > MAX_CONTEXT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Conversation context is too long ({len(context)} chars). "
                   f"The limit is {MAX_CONTEXT_CHARS}.",
        )

    question = q if not context else f"{context.strip()}\n\nFollow-up question: {q}"
    # additive client hint (UI sends browser timezone + local time): lets
    # "what time is it?" answer without asking the user's location
    if tz and local_time:
        q = f"[Client local time: {local_time} ({tz})]\n{q}"

    raw_smalltalk = memory_layer._is_smalltalk(q)

    async def gen():
        t_ask = time.time()
        answer_chars = 0
        route = "smalltalk" if raw_smalltalk else "brain"
        ask_error = None
        yield json.dumps({"stage": "start", "dataset": dataset or DEMO_DATASET}) + "\n"
        try:
            async for event in recall(question, dataset, smalltalk=raw_smalltalk):
                if event.get("type") == "chunk":
                    answer_chars += len(event.get("text") or "")
                # P5: the route actually taken, from the orchestrator's own
                # stage labels — this is the per-route cost split dimension.
                label = event.get("label", "")
                if label.startswith("Smalltalk"):
                    route = "smalltalk"
                elif label.startswith("Router: general chat"):
                    route = "chat"
                elif event.get("stage") == "error":
                    ask_error = event.get("message")
                yield json.dumps(event) + "\n"
        except Exception as exc:  # noqa: BLE001 - demo must never white-screen
            # S6: truncate — the untruncated tenant traceback/paths/SQL used
            # to echo to every caller on this one path.
            ask_error = str(exc)[:300]
            yield json.dumps({"stage": "error", "message": ask_error}) + "\n"
        yield json.dumps({"stage": "done"}) + "\n"
        ms_total = int((time.time() - t_ask) * 1000)
        # metering (P2): estimates = chars/4; the true provider usage lives in
        # the provider dashboard until a usage-exposing recall path exists
        storage.save_llm_call(
            brain=dataset or DEMO_DATASET, feature="ask",
            model=os.getenv("LLM_MODEL", "brain-llm"),
            est_prompt_tokens=len(question) // 4,
            est_completion_tokens=answer_chars // 4,
            ms=ms_total,
        )
        # P5 observability: the same estimate, now with the route dimension,
        # posted fire-and-forget to Langfuse (no-op without keys).
        observe.trace(
            feature="ask", brain=dataset or DEMO_DATASET, route=route,
            model=os.getenv("LLM_MODEL", "brain-llm"),
            user=(identity or {}).get("user_id"),
            est_prompt=len(question) // 4, est_completion=answer_chars // 4,
            ms=ms_total, ok=ask_error is None, error=ask_error,
            started_at=t_ask,
        )

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.get("/api/graph")
def graph(request: Request, dataset: str | None = None):
    """The knowledge graph, for the graph view."""
    dataset = safe_dataset(dataset)
    require_dataset_access(request, dataset)
    g, source = _load_graph(dataset)
    if g is None:
        return {"error": source, "nodes": [], "edges": []}
    g["source"] = source
    return g


@app.get("/api/stats")
def stats(request: Request, dataset: str | None = None):
    """Graph size — cheap numbers that make the graph feel real.

    Uses /graph rather than /graph-summary: the summary endpoint returns
    numNodes 0 until a summary run has been computed, which would render as
    a confidently empty graph.
    """
    dataset = safe_dataset(dataset)
    require_dataset_access(request, dataset)
    target = safe_dataset(dataset)
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

# --------------------------------------------------------------------------
# PR-7: durable lifecycle (flag-gated — the legacy route above stays default)
# --------------------------------------------------------------------------

def _jobs_v2_enabled() -> bool:
    return os.getenv("KESTREL_JOBS_V2", "0") == "1"


@app.post("/api/brains/v2")
async def create_brain_v2(request: Request, name: str = Form(...),
                          files: list[UploadFile] = File(...),
                          idempotency_key: str = Form(...)):
    """202 create through the durable job path (KESTREL_JOBS_V2=1 only).

    Reservation + staging are atomic and tenant-free; ingestion happens in
    the worker with per-file outcomes and publish fencing. 409 covers both
    same-workspace slug conflicts and idempotency-key mismatches."""
    if not _jobs_v2_enabled():
        raise HTTPException(status_code=404, detail="Not found.")
    if memory_layer.PROVIDER != "cloud":
        raise HTTPException(status_code=400, detail="Uploads need the cloud provider.")
    safe = normalize_brain_name(name)
    if not safe:
        raise HTTPException(status_code=400, detail="Brain name must be 3-40 characters.")
    if safe in RESERVED_NAMES:
        raise HTTPException(status_code=400, detail=f"'{safe}' is reserved.")
    identity = require_tenant(request)
    _check_rate(request, "upload")
    if len(files) > documents.MAX_FILES:
        raise HTTPException(status_code=413, detail=f"Too many files: {len(files)}.")
    payload = [(f.filename or "untitled", await _read_capped(f, documents.MAX_FILE_BYTES))
               for f in files]
    if not any(b for _, b in payload):
        raise HTTPException(status_code=400, detail="No files were uploaded.")
    import lifecycle
    try:
        result = lifecycle.create_brain_v2(identity or {"user_id": "local", "org_id": None},
                                           safe, payload, idempotency_key)
    except lifecycle.SlugConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except lifecycle.IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=f"Idempotency conflict: {exc}") from exc
    observe.trace(feature="brain-create-v2",
                  user=(identity or {}).get("user_id"))
    return JSONResponse(result, status_code=202)


@app.get("/api/jobs/{job_id}")
def job_status_v2(request: Request, job_id: str):
    if not _jobs_v2_enabled():
        raise HTTPException(status_code=404, detail="Not found.")
    identity = require_tenant(request)
    import lifecycle
    st = lifecycle.job_status(job_id)
    if not st:
        raise HTTPException(status_code=404, detail="No such job.")
    if auth.active():
        import lifecycle
        with lifecycle._conn() as conn, conn.cursor() as cur:
            row = cur.execute(
                """select w.clerk_org_id from brain_jobs j
                   join workspaces w on w.id = j.workspace_id where j.id = %s""",
                (job_id,)).fetchone()
        if not row or row["clerk_org_id"] != (identity or {}).get("org_id"):
            raise HTTPException(status_code=403, detail="This job belongs to another workspace.")
    return {"ok": True, **st}


@app.post("/api/jobs/{job_id}/cancel")
def job_cancel_v2(request: Request, job_id: str):
    if not _jobs_v2_enabled():
        raise HTTPException(status_code=404, detail="Not found.")
    identity = require_tenant(request)
    import lifecycle
    return {"ok": lifecycle.request_cancel(job_id), "requested": True}


@app.on_event("startup")
def _start_lifecycle_worker() -> None:
    if _jobs_v2_enabled():
        import lifecycle
        lifecycle.start_worker()


@app.on_event("startup")
def _log_provider_state() -> None:
    # Phase 11: startup checks — the active LLM route is visible in logs,
    # not just /health (no secrets: base host + model id only).
    import llm as _llm
    base = (_llm.base_url() or "no-provider")
    print(f"[startup] llm route={os.getenv('KESTREL_LLM_ROUTE', 'auto')} "
          f"base={base} model={_llm.default_model()} "
          f"nova_status={_llm.nova_probe_status()}")


@app.get("/api/brains")
def list_brains(request: Request):
    """Every brain on the tenant. Sizes are fetched per row by the dashboard."""
    # LOW-10: the tenant's brain inventory is per-account data — require a
    # caller in Clerk mode. Auth-off keeps the old open behavior.
    require_tenant(request)
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
    request: Request,
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

    # Identity first, always: the exists() probe below hits the tenant, and
    # branching on its result before gating would turn name-existence into an
    # oracle for unauthenticated callers.
    identity = require_tenant(request)

    # Refuse to merge into an existing brain UNLESS the caller explicitly asked
    # to. Silently appending to a brain the user thinks is new would produce
    # answers from documents they never saw — so the 409 is the default, and
    # `append=True` is the opt-in the UI offers once the user has been told.
    held_claim = False          # M4: set only when WE reserved this name below
    claim_org: str | None = None
    claim_uid: str | None = None
    try:
        already_exists = cognee_cloud.exists(safe)
    except Exception as exc:  # noqa: BLE001 - tenant-down is availability
        # Without the tenant we cannot tell existing from new, and proceeding
        # unseen could merge into a brain the user was never told about (the
        # exact failure the 409 below exists to prevent). Fail closed, and
        # say so: 503 (retry later) instead of a 500 that reads as our crash.
        raise HTTPException(
            status_code=503,
            detail=(
                "The brain service is unreachable right now - new brains "
                "cannot be checked or created. Please try again in a moment."
            ),
        ) from exc
    if already_exists:
        # Appending to SOMEONE ELSE'S dataset must fail closed — the owner
        # check applies to the existing brain.
        require_dataset_access(request, safe)
        if not append:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"A brain called '{safe}' already exists. Add to it instead, "
                    "or pick another name."
                ),
            )
    else:
        # S3: a genuinely new brain has no ownership row by definition — the
        # SEC-2 fail-closed rule would 403 every legitimate create. Any
        # authenticated identity may found a brain (identity already gated
        # above); ownership is stamped at success (SEC-9) so the second
        # request already answers to it.
        #
        # M4: and now the name is RESERVED before any work starts, which is
        # what the probe could never do. `exists()` reports the past, so two
        # concurrent creates both heard "new", both ingested, and the dataset
        # was credited to whichever writer inserted its ownership row first -
        # leaving the other tenant's documents inside a brain it could no
        # longer reach. A claim is a reservation, not an observation.
        ident = getattr(request.state, "identity", None) or {}
        claim_org, claim_uid = ident.get("org_id"), ident.get("user_id")
        if auth.active():
            verdict = storage.claim_brain(safe, claim_org, claim_uid)
            if verdict == "unavailable":
                # Without a recorded claim there is no exclusivity, and running
                # an unreserved create is exactly the race this closes.
                raise HTTPException(
                    status_code=503,
                    detail=("The brain service cannot record ownership right now, "
                            "so this name cannot be reserved safely. Please try "
                            "again in a moment."),
                )
            if verdict == "taken":
                raise HTTPException(
                    status_code=409,
                    detail=(f"A brain called '{safe}' is being created right now. "
                            "Try again in a moment, or pick another name."),
                )
            # 'claimed' / 'retry' / 'stolen' mean WE hold an in-flight claim and
            # must drop it if the work fails; 'owned' is our own finished brain
            # whose dataset went missing, so its row stays as it is.
            held_claim = verdict in ("claimed", "retry", "stolen")

    def drop_claim() -> None:
        if held_claim:
            storage.release_brain_claim(safe, claim_org, claim_uid)

    # Cap the count before reading anything, then cap each file WHILE reading it.
    # S5: uploads cost embedding + LLM — bound per caller like asks.
    _check_rate(request, "upload")
    if len(files) > documents.MAX_FILES:
        drop_claim()
        raise HTTPException(
            status_code=413,
            detail=f"Too many files: {len(files)}. The limit is {documents.MAX_FILES}.",
        )

    payload = [
        (upload.filename or "untitled", await _read_capped(upload, documents.MAX_FILE_BYTES))
        for upload in files
    ]
    if not payload:
        drop_claim()
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    # Parsing a PDF or DOCX is CPU-bound and synchronous. Running it inline in an
    # async handler stalls the entire event loop, including /health — which Render
    # uses as a liveness probe, so a slow parse could get the service restarted
    # mid-demo. Push it to a worker thread.
    docs, failures = await asyncio.to_thread(documents.extract_many, payload)
    if not docs:
        drop_claim()
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
        drop_claim()
        reasons = "; ".join(
            f"{r['name']}: {r.get('error', 'unknown error')}" for r in failed[:5]
        )
        raise HTTPException(
            status_code=502,
            detail=f"None of the documents could be ingested. {reasons}",
        )

    # SEC-9: register ownership only AFTER the dataset is confirmed created.
    # Registering before validation/extraction left stale owner rows for brains
    # that never existed — and ON CONFLICT DO NOTHING then credited a later,
    # successful create by another org to the first failed writer.
    # P3: org-owned brains are only reachable by their workspace
    # (brain_allowed enforces it on read).
    identity = getattr(request.state, "identity", None) or {}
    if auth.active():
        storage.register_brain(safe, identity.get("org_id"),
                               identity.get("user_id"), shared=False)
        # M4: the reservation becomes a fact. The claim is flipped here, and only
        # here, because a brain may only be owned once its dataset actually
        # exists - a 'creating' row is a claim, a 'ready' row is a brain.
        storage.mark_brain_ready(safe)

    # Record which filenames went into this brain so its answers can cite the
    # files the user actually chose. The tenant will not store document names
    # for us — `remember` accepts a `filename` field and silently ignores it —
    # so this local manifest is the only way an uploaded brain can cite itself.
    try:
        import citations

        # H2: record only the documents that ACTUALLY landed. Passing all of
        # `docs` recorded the failed ones too, so a brain could cite a source
        # file that is not in its graph - a false citation, which is the one
        # thing this product exists to prevent.
        landed = {r["name"] for r in succeeded}
        stored = [d for d in docs if d["name"] in landed]
        await asyncio.to_thread(citations.record_upload, safe, stored)
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
async def brain_events(request: Request, name: str, timeout_s: int = 600):
    # H4: timeout_s is client-controlled. Unclamped, `?timeout_s=99999999`
    # returns 200 and holds a connection polling the tenant for years.
    timeout_s = max(10, min(timeout_s, 900))
    # SEC-3: this stream used to have no auth gate at all. Normalize first
    # (same edge rule as every other route), then authorize.
    name = safe_dataset(name)
    require_dataset_access(request, name)
    # S5: a 900s held connection per call — bound per caller.
    _check_rate(request, "events")
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
def delete_brain(request: Request, name: str):
    """Remove a brain.

    RESERVED_NAMES is enforced here as well as in create_brain. The UI hides the
    delete button for the demo and system brains, but the API is the real
    boundary — and `DELETE /api/brains/default_dataset` would otherwise delete
    Cognee's own internal dataset. The demo guard also lives inside
    cognee_cloud.delete_dataset, so neither layer can be bypassed on its own.
    """
    # SEC-1: normalize FIRST, then authorize the normalized name. The authz
    # rule looks rows up exactly and rows are stored normalized — authorizing
    # the raw segment let a case-variant (no row → allow) delete someone
    # else's brain after normalization. One name, one meaning, start to finish.
    # (Authorisation still evaluated BEFORE the mode guard: an unauthorized
    # caller must get 401/403 regardless of provider mode. Found by
    # test_tenants under the mock-forced battery.)
    safe = normalize_brain_name(name)
    # M1: create_brain REFUSES a name that fails normalisation; delete used to
    # fall through and pass the raw name to delete_dataset. The two routes must
    # agree about what a valid name is - and delete is the dangerous one.
    if not safe:
        raise HTTPException(
            status_code=400,
            detail=(
                "Brain name must be 3-40 characters, using letters, numbers or "
                "underscores."
            ),
        )
    require_dataset_access(request, safe)

    if memory_layer.PROVIDER != "cloud":
        raise HTTPException(status_code=400, detail="Deletion needs PROVIDER=cloud.")

    # Normalise first, so a case trick such as "Company_Brain" cannot slip past
    # the reserved check and then match an existing dataset.
    if safe in RESERVED_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"'{safe}' is reserved and cannot be deleted.",
        )

    try:
        import cognee_cloud

        removed = cognee_cloud.delete_dataset(safe)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)[:300]) from exc
    if not removed:
        raise HTTPException(status_code=404, detail=f"No brain called '{name}'.")
    # S2: the dataset is gone — release the name. Without this the ownership
    # row squats the name and a later re-create by anyone 403s on it.
    if auth.active():
        storage.unregister_brain(safe)
    return {"ok": True, "deleted": safe}


# --------------------------------------------------------------------------
# reading a source document back
# --------------------------------------------------------------------------

@app.get("/api/source")
def source(request: Request, name: str, dataset: str | None = None):
    """Return the text of a cited source document, so a citation is checkable.

    A citation you cannot open is an assertion. This makes it verifiable.

    Path safety: only a bare filename is accepted - no separators, no parent
    references - and the resolved path is re-checked to be inside corpus/
    before it is read. `basename` alone is not enough on its own, so both
    checks run.
    """
    dataset = safe_dataset(dataset)
    require_dataset_access(request, dataset)

    if not name or not re.fullmatch(r"[A-Za-z0-9._ -]{1,120}", name):
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
    target = safe_dataset(dataset)
    if target == DEMO_DATASET:
        raise HTTPException(status_code=404, detail=f"No source document called '{name}'.")

    # Phase 8: durable provenance first — a v2-created brain resolves from the
    # app's own tables, not from the uploads manifest.
    import citations
    durable_text = citations.durable_source(target, name)
    if durable_text:
        return {"ok": True, "name": name, "source": "durable", "text": durable_text}

    try:
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
    """The product frontend: React when asked for and built, legacy otherwise.

    Both are the same product on the same origin and the same API; KESTREL_UI
    decides which one a browser gets. When react is selected but the bundle is
    missing, this serves legacy AND says so in the log — the alternative (a
    silent fallback) is how a deploy ends up on the wrong UI without anyone
    noticing.
    """
    if UI_MODE == "react":
        if react_available():
            # Same no-cache rule as _page(): index.html is unhashed and names
            # the hashed bundle, so a cached copy pins an old build.
            return FileResponse(
                _dist_file("index.html"),
                headers={
                    "Cache-Control": "no-cache, must-revalidate",
                    "Pragma": "no-cache",
                },
            )
        print(
            "KESTREL_UI=react but frontend/dist/index.html is missing — "
            "serving the legacy dashboard. Run ops/build_frontend.sh.",
            flush=True,
        )
    return _page("index.html")


@app.get("/favicon.svg")
def favicon():
    """dist/index.html asks for /favicon.svg; without this it 404s on every
    load (a console error, which the UI smoke suite treats as a failure)."""
    if UI_MODE == "react" and os.path.isfile(_dist_file("favicon.svg")):
        return FileResponse(_dist_file("favicon.svg"), media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="No favicon.")


@app.get("/icons.svg")
def icons_sprite():
    if UI_MODE == "react" and os.path.isfile(_dist_file("icons.svg")):
        return FileResponse(_dist_file("icons.svg"), media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="No icon sprite.")


@app.get("/graph")
def graph_page():
    return _page("graph.html")


# The brains and upload pages have React equivalents (BrainsPage, and the
# create-brain dialog + files sheet), so those two legacy pages are retired:
# the HTML files are gone and the URLs redirect into the app. Nothing links to
# them any more except old bookmarks and the legacy shell's own nav, which the
# redirect keeps working. /graph stays until the in-app graph is equivalent —
# it is a genuinely richer surface (force layout, expansion, inspector) and the
# React view labels it as the full version.
@app.get("/brains")
def brains_page():
    return RedirectResponse("/?view=brains", status_code=307)


@app.get("/upload")
def upload_page():
    return RedirectResponse("/?view=brains&new=1", status_code=307)


if __name__ == "__main__":
    import uvicorn

    # O7: a missing JWKS URL in clerk mode is a silent total outage (every
    # token 401s behind a green /health). Fail LOUD at boot instead.
    if auth.mode() == "clerk" and not auth.jwks_url():
        raise SystemExit(
            "AUTH_MODE=clerk but no CLERK_JWKS_URL (or CLERK_ISSUER) is set — "
            "every request would 401. Refusing to boot.")
    if auth.mode() == "clerk":
        print(f"auth: clerk mode, JWKS {auth.jwks_url()}", flush=True)
    # Which frontend "/" will hand a browser — printed at boot so a deploy's
    # logs answer "is the React UI live?" without opening a browser.
    if UI_MODE == "react" and react_available():
        print(f"ui: react (frontend/dist, {DIST_DIR})", flush=True)
    elif UI_MODE == "react":
        print("ui: react REQUESTED but frontend/dist is missing — serving the "
              "legacy dashboard. Run ops/build_frontend.sh.", flush=True)
    else:
        print("ui: legacy (static/index.html; set KESTREL_UI=react to serve "
              "frontend/dist)", flush=True)
    if not storage.available():
        print("storage: Postgres unavailable — chats fall back to "
              "localStorage; Clerk-mode brains will 403 until it connects.",
              flush=True)

    # Render injects PORT and requires binding to 0.0.0.0. Locally we want
    # 127.0.0.1. Same file works in both places with these two defaults.

    # Render injects PORT and requires binding to 0.0.0.0. Locally we want
    # 127.0.0.1. Same file works in both places with these two defaults.
    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )
