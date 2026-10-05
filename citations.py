"""Turn opaque citation IDs into real source filenames plus a verbatim excerpt.

THE PROBLEM
Cognee returns evidence like:

    chunk 1 of document text_cfa979402db25ffb287 (data_id: ..., chunk_id: ...)

That proves a chunk exists. It does not tell a judge WHICH document it came from
or WHAT it says — so "grounded in retrieved knowledge" was an assertion rather
than something you could see. Meanwhile the offline fixtures hand-wrote filenames
and excerpts, which meant the fallback looked MORE grounded than production.

THE FIX
Every ingested document is stored as a data item whose raw content is the exact
text we sent. So for each data item we fetch the raw content, fingerprint it, and
match it against the local corpus by content. That yields a real filename without
re-ingesting anything, which keeps the demo graph byte-identical.

Matching by CONTENT rather than by filename is deliberate: the tenant was never
told our filenames (the upload path sends raw text), so content is the only
reliable join key. It also means the mapping is verifiable — if the fingerprints
do not match, we return nothing rather than guessing.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "corpus")

# {dataset: {fingerprint: filename}} for user-uploaded files. Written at upload
# time because the tenant will not store a document's name for us.
# O3b: this manifest fingerprints user-uploaded file content — which once
# embedded a live key fragment that got committed. It lives OUTSIDE git now
# (cognee_oss_state/ is gitignored): local operational state, not source.
UPLOADS = os.path.join(HERE, "cognee_oss_state", "uploads.json")

# How long a resolved map stays warm. The tenant only changes when something is
# ingested, and this saves a round trip per question.
_TTL_SECONDS = 300

_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()
_id_cache: dict = {}        # {dataset: {data_id: {source, excerpt}}} — persistent
_items_cache: dict = {}     # {dataset: (ts, {id: name})}
_prewarm_events: dict = {}  # {dataset: Event} — set when the dataset is cached
_prewarm_lock = threading.Lock()

# "chunk 1 of document text_abc (data_id: xyz, chunk_id: 123)"
_DATA_ID_RE = re.compile(r"data_id:\s*([0-9a-fA-F-]{8,})")

# Cognee's name for a document that was ingested without one: "text_<hash>".
# Anything matching this tells us nothing, so we fall back to content matching.
_GENERATED_NAME_RE = re.compile(r"^text_[0-9a-f]{16,}$", re.IGNORECASE)


_FINGERPRINT_LEN = 120


def _fingerprint(text: str, length: int = _FINGERPRINT_LEN) -> str:
    """A whitespace-insensitive prefix, for matching raw content to a corpus file."""
    return re.sub(r"\s+", " ", text or "").strip().lower()[:length]


def _corpus_fingerprints() -> dict[str, str]:
    """{fingerprint: filename} for every file in corpus/, ambiguous prefixes dropped.

    A fingerprint is 120 normalised characters, so two documents that open the same way
    collide. This map used to be last-writer-wins, which meant the alphabetically later
    file silently owned both citations. An ambiguous fingerprint now names nothing: the
    caller shows no source rather than the wrong one.
    """
    out: dict[str, str] = {}
    if not os.path.isdir(CORPUS):
        return out
    owners: dict[str, list[str]] = {}
    for name in sorted(os.listdir(CORPUS)):
        path = os.path.join(CORPUS, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                fp = _fingerprint(handle.read())
        except OSError:
            continue
        # An empty or whitespace-only file fingerprints to "", which is also what a
        # FAILED raw fetch fingerprints to — so it would lend its name to every
        # document we could not read.
        if not fp:
            continue
        owners.setdefault(fp, []).append(name)
    for fp, names in owners.items():
        if len(names) == 1:
            out[fp] = names[0]
    return out


def _manifest() -> dict:
    """uploads.json parsed once. Every reader below takes it as an argument, so one
    `_name_map` call does not open and parse the file twice."""
    try:
        with open(UPLOADS, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def _upload_fingerprints(dataset: str, manifest: dict | None = None) -> dict[str, str]:
    """{fingerprint: filename} for files uploaded into this brain."""
    manifest = _manifest() if manifest is None else manifest
    return {k: v for k, v in (manifest.get(dataset) or {}).items()
            if isinstance(v, str)}


def _collided_fingerprints(dataset: str, manifest: dict) -> set[str]:
    """Fingerprints record_upload proved ambiguous for THIS brain.

    COR-8 keeps the first name and records the loser under uploads.json's
    `_collisions`, and until now nothing read it back — so a known-ambiguous fingerprint
    still resolved to whichever name the manifest happened to keep. The key is
    `{dataset}::{full fingerprint}`: it used to be truncated to 32 characters, and a
    reader matching on that prefix deleted every document that merely OPENED like a
    colliding pair. 32 normalised characters is five words of boilerplate, and ambiguity
    is a property of the whole 120-character fingerprint, which is what is matched now.
    Records in the old short form are ignored rather than prefix-matched; A-57 measured
    zero collision groups in the live manifest, so nothing is being dropped on the floor.
    """
    head = f"{dataset}::"
    return {key[len(head):] for key in (manifest.get("_collisions") or {})
            if key.startswith(head) and len(key) - len(head) == _FINGERPRINT_LEN}


def _name_map(dataset: str) -> dict[str, str]:
    """The one {fingerprint: filename} map every resolver is built from.

    Two sources of truth for "which filename is this?": `corpus/` (the pre-built demo
    documents) and `uploads.json` (files a user uploaded, recorded at upload time).
    Content is the join key, because the tenant accepts a `filename` field and silently
    ignores it, so every document lands as `text_<hash>`.

    Uploads win over the corpus for identical content: the tenant calls the file what
    they uploaded it as, and the demo's filename would be the wrong label. What gets
    dropped is ambiguity — a fingerprint two corpus files share, or one the collision
    table says belongs to two uploads. A dropped fingerprint shows no filename, which
    is the honest answer; a guessed one is a fabricated citation.
    """
    manifest = _manifest()
    out = _corpus_fingerprints()
    for fp, name in _upload_fingerprints(dataset, manifest).items():
        out[fp] = name
    for fp in _collided_fingerprints(dataset, manifest):
        out.pop(fp, None)
    return out


def record_upload(dataset: str, documents: list) -> None:
    """Remember which filenames went into a brain the user just built.

    The tenant will not store a document's name for us — `remember` accepts a
    `filename` field and silently ignores it, so every document lands as
    `text_<hash>`. Recording the fingerprint locally is therefore the only way an
    uploaded brain can cite the file the user actually chose.

    Never raises: a manifest write is an enhancement, and losing it must not fail
    an upload that already succeeded.
    """
    if not documents:
        return
    with _lock:
        try:
            with open(UPLOADS, encoding="utf-8") as handle:
                manifest = json.load(handle)
        except (OSError, ValueError):
            manifest = {}

        entry = manifest.setdefault(dataset, {})
        collisions = manifest.setdefault("_collisions", {})
        for doc in documents:
            text = doc.get("text") or ""
            name = doc.get("name")
            if not (name and text):
                continue
            # COR-8: first writer wins within a dataset, and a collision is
            # recorded visibly instead of silently overwriting — a citation
            # must never resolve to the wrong file quietly. (Resolution
            # already prefers the tenant's stored real names; the fingerprint
            # is only the fallback for text_<hash> items.)
            fp = _fingerprint(text)
            prior = entry.get(fp)
            if prior is None:
                entry[fp] = name
            elif prior != name:
                # Full fingerprint, not a truncation: the reader matches this key
                # exactly, and a 32-character version of it also suppressed every
                # document that merely opened with the same five words.
                key = f"{dataset}::{fp}"
                seen = collisions.setdefault(key, [])
                for n in (prior, name):
                    if n not in seen:
                        seen.append(n)

        try:
            os.makedirs(os.path.dirname(UPLOADS), exist_ok=True)
            with open(UPLOADS, "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=1, sort_keys=True)
        except OSError:
            return

        # M6: dropped inside the lock. Popping it after releasing let a
        # concurrent for_dataset() repopulate the stale entry in the gap, so the
        # next question would read the pre-upload map anyway.
        _cache.pop(dataset, None)


def _fetch_map(dataset: str) -> dict:
    """{data_id: {"source": filename|None, "excerpt": str}} for one dataset."""
    import cognee_cloud

    # Two sources of truth for "which filename is this?", both joined by content and
    # both ambiguity-filtered — see _name_map.
    names = _name_map(dataset)
    resolved: dict = {}

    dataset_id = cognee_cloud.resolve_id(dataset)
    items = cognee_cloud.data_items(dataset_id)

    # The raw fetches are the latency here — one HTTP round-trip per document,
    # all independent. In parallel they finish in the time of the slowest one
    # instead of their sum, which is what made citations trail the answer.

    ids = [item.get("id") for item in items if item.get("id")]

    def fetch_raw(data_id):
        try:
            return data_id, cognee_cloud.data_raw(dataset_id, data_id)
        except Exception:  # noqa: BLE001 - a missing raw must not break the answer
            return data_id, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        raws = dict(pool.map(fetch_raw, ids))

    for item in items:
        data_id = item.get("id")
        if not data_id:
            continue
        raw = raws.get(data_id)

        excerpt = re.sub(r"\s+", " ", raw or "").strip()

        # Prefer the name the document was ingested under. It is the filename
        # the user actually uploaded, which beats anything we can infer. Only
        # fall back to content matching when the name is Cognee's generated
        # "text_<hash>" placeholder.
        stored = (item.get("name") or "").strip()
        named = stored if stored and not _GENERATED_NAME_RE.match(stored) else None

        resolved[data_id] = {
            # None is an honest answer: we would rather show no filename than a
            # wrong one.
            "source": named or names.get(_fingerprint(raw)),
            "excerpt": excerpt[:220],
        }
    return resolved


def for_dataset(dataset: str) -> dict:
    """Cached {data_id: {source, excerpt}} for a dataset."""
    now = time.time()
    with _lock:
        hit = _cache.get(dataset)
        if hit and now - hit[0] < _TTL_SECONDS:
            return hit[1]
    try:
        resolved = _fetch_map(dataset)
    except Exception:  # noqa: BLE001 - citations are an enhancement, never fatal
        # H4: never cache a failure. Caching {} poisoned source resolution for
        # the full TTL after a single transient blip — return the stale map if
        # there is one, else empty, and let the next call retry fresh.
        with _lock:
            hit = _cache.get(dataset)
            return hit[1] if hit else {}
    with _lock:
        _cache[dataset] = (now, resolved)
        _bound(_cache)
    return resolved


def _bound(cache: dict, limit: int = 50) -> None:
    """H6: cap process-lifetime caches — dataset keys are caller-influenced,
    so an unbounded map is a memory leak per unique name."""
    while len(cache) > limit:
        cache.pop(next(iter(cache)))


def _data_items_cached(dataset: str) -> dict:
    """{data_id: stored-name} for one dataset, TTL-cached."""
    import cognee_cloud

    now = time.time()
    hit = _items_cache.get(dataset)
    if hit and now - hit[0] < _TTL_SECONDS:
        return hit[1]
    dataset_id = cognee_cloud.resolve_id(dataset)
    m = {
        i.get("id"): (i.get("name") or "").strip()
        for i in cognee_cloud.data_items(dataset_id)
        if i.get("id")
    }
    _items_cache[dataset] = (now, m)
    _bound(_items_cache)
    return m


def prewarm(dataset: str) -> None:
    """Resolve every document in a dataset into the persistent cache.

    Exactly ONE caller per dataset does the fetching; concurrent callers
    (the orchestrator's prewarmer, an enrich()) wait on the same event and
    then read the finished store. This is what makes citations cost 0s after
    the answer: the fetches overlapped the retrieval instead of trailing it.
    """
    dataset = dataset or "default"
    with _prewarm_lock:
        ev = _prewarm_events.get(dataset)
        if ev is None:
            ev = threading.Event()
            _prewarm_events[dataset] = ev
            _bound(_prewarm_events)
            owner = True
        else:
            owner = False
    if not owner:
        # H5: bounded join — the trailing citations wait was up to 60s for a
        # best-effort enrichment that already missed its overlap window.
        ev.wait(timeout=15)
        return
    try:
        _prewarm_fill(dataset)
    finally:
        ev.set()
        # H6: drop the event once set — waiters hold their own ref; late
        # joiners simply become owners. Otherwise one entry leaks per dataset
        # name, and names are caller-influenced.
        with _prewarm_lock:
            if _prewarm_events.get(dataset) is ev:
                del _prewarm_events[dataset]


def _prewarm_fill(dataset: str) -> None:
    items_map = _data_items_cached(dataset)
    store = _id_cache.setdefault(dataset, {})
    _bound(_id_cache)
    missing = [d for d in items_map if d not in store]
    if not missing:
        return
    import cognee_cloud

    dataset_id = cognee_cloud.resolve_id(dataset)
    names = _name_map(dataset)

    def fetch(did):
        try:
            raw = cognee_cloud.data_raw(dataset_id, did)
        except Exception:  # noqa: BLE001
            raw = None
        excerpt = re.sub(r"\s+", " ", raw or "").strip()
        named = (items_map.get(did) or "").strip()
        named = None if _GENERATED_NAME_RE.match(named) else (named or None)
        store[did] = {
            "source": named or names.get(_fingerprint(raw)),
            "excerpt": excerpt[:220],
        }

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(fetch, missing))


def data_id_from(reference) -> str | None:
    """Pull a data_id out of a Cognee evidence string."""
    match = _DATA_ID_RE.search(str(reference))
    return match.group(1) if match else None


def _rows(sql: str, params: tuple) -> list[dict]:
    """One read-only query against the app's own provenance tables.

    A seam as much as a helper: these two lookups are the only place citations touch
    Postgres, and tests replace this function to prove the ambiguous-row handling
    without needing a server. Writes never belong here.

    A failed query raises after marking storage down (the CH-8 rule the rest of the
    app follows) — "we could not ask" is not the same fact as "there is no row", and
    the difference is what S8 turns into a 503 instead of a 404.
    """
    from storage import DATABASE_URL, db_error, mark_down
    import psycopg
    try:
        with psycopg.connect(DATABASE_URL, row_factory=psycopg.rows.dict_row) as conn, \
                conn.cursor() as cur:
            return list(cur.execute(sql, params).fetchall())
    except db_error as exc:
        mark_down(f"citations: {exc}")
        raise


def _durable_reference(dataset: str, did: str):
    """Phase 8: exact provenance from the app's own tables (v2-created brains).

    Returns {source, excerpt, generation_id, document_version_id} or None. Only rows
    the v2 verification actually wrote are consulted — nothing is inferred from names
    or fingerprints.

    This used to be `limit 1` with no `ORDER BY`, and that was not academic:
    `backend_data_id` identifies CONTENT, so the same file inside two brains — or inside
    two generations of one brain — matches twice, and the citation then named whichever
    row the planner reached first. Two candidates are read in a fixed order; a genuine
    clash answers None, which the caller renders as unresolved, rather than guessing at
    someone's document.
    """
    try:
        rows = _rows(
            """select gd.document_version_id, gd.generation_id,
                      doc.filename, dv.exact_extracted_text
               from generation_documents gd
               join brain_generations g on g.id = gd.generation_id
               join brains b on b.id = g.brain_id
               join document_versions dv on dv.id = gd.document_version_id
               join documents doc on doc.id = dv.document_id
               where (b.slug = %s or g.backend_dataset_name = %s)
                 and gd.backend_data_id = %s
               order by gd.generation_id, gd.document_version_id
               limit 2""", (dataset, dataset, did))
    except Exception:  # noqa: BLE001 - durable lookup is best-effort like the rest
        return None
    if not rows:
        return None
    if len({(r["generation_id"], r["document_version_id"]) for r in rows}) > 1:
        return None
    row = rows[0]
    text = row["exact_extracted_text"] or ""
    return {"source": row["filename"],
            "excerpt": re.sub(r"\s+", " ", text).strip()[:220],
            "generation_id": row["generation_id"],
            "document_version_id": row["document_version_id"]}


def durable_source(dataset: str, filename: str, document_version_id: str | None = None):
    """Reverse lookup for /api/source: the durable text behind an uploaded document.

    With a version id — which is what a citation carries now — exactly that version is
    read, and only if it belongs to the brain the caller was authorised for. With none,
    today's behaviour is kept and deliberately so: every chat saved before this change
    has no id, and the newest version is what they have always opened. That IS the wrong
    answer for an old citation whose document was re-uploaded, which is why the id is
    threaded through the payload rather than patched around here.
    """
    if document_version_id:
        clause, params = " and dv.id = %s", (dataset, filename, document_version_id)
    else:
        clause, params = "", (dataset, filename)
    from storage import db_error
    try:
        rows = _rows(
            """select dv.exact_extracted_text
               from documents doc
               join brains b on b.id = doc.brain_id
               join document_versions dv on dv.document_id = doc.id
               where b.slug = %s and doc.filename = %s""" + clause + """
               order by dv.created_at desc limit 1""", params)
    except db_error:
        # "We could not ask" is not "there is no such document". The route turns this
        # into a 503; swallowing it here would let the caller fall through to another
        # source, which is exactly the substitution the invariant forbids.
        raise
    except Exception:  # noqa: BLE001
        return None
    if rows and rows[0]["exact_extracted_text"]:
        return rows[0]["exact_extracted_text"]
    return None


def enrich(references: list, dataset: str) -> list:
    """Attach source + excerpt to each evidence string.

    Latency-critical: this runs while the answer streams. Only the CITED
    documents are fetched (never the whole dataset), each resolved document is
    cached for the process lifetime, and the fetches run in parallel — repeat
    questions resolve in 0s, first ones in about one round-trip.
    """
    if not references:
        return []
    dataset = dataset or "default"
    # COR-4: the id map is best-effort — a lookup failure here used to
    # propagate past `done` and mislabel a complete answer as dropped.
    try:
        items_map = _data_items_cached(dataset)
    except Exception:  # noqa: BLE001
        items_map = {}
    store = _id_cache.setdefault(dataset, {})
    _bound(_id_cache)

    cited = []
    seen = set()
    for ref in references:
        did = data_id_from(ref)
        if did and did not in seen:
            seen.add(did)
            cited.append(did)

    # if a prewarm for this dataset is running (the orchestrator started it
    # when the question arrived), join it — its fetches overlapped the
    # retrieval, so this wait is usually 0s (bounded at 15s per H5).
    ev = _prewarm_events.get(dataset)
    if ev and not ev.is_set():
        ev.wait(timeout=15)

    missing = [d for d in cited if d not in store]
    if missing:
        # COR-4 (cont.): resolving the dataset itself can fail (unknown
        # dataset, tenant down) — that must yield unresolved refs, not raise.
        try:
            import cognee_cloud

            dataset_id = cognee_cloud.resolve_id(dataset)
        except Exception:  # noqa: BLE001
            dataset_id = None
        if dataset_id is not None:
            names = _name_map(dataset)

            def fetch(did):
                durable = _durable_reference(dataset, did)
                if durable and durable.get("source"):
                    store[did] = durable
                    return
                try:
                    raw = cognee_cloud.data_raw(dataset_id, did)
                except Exception:  # noqa: BLE001 - a missing raw must not break the answer
                    raw = None
                excerpt = re.sub(r"\s+", " ", raw or "").strip()
                named = (items_map.get(did) or "").strip()
                named = None if _GENERATED_NAME_RE.match(named) else (named or None)
                store[did] = {
                    "source": named or names.get(_fingerprint(raw)),
                    "excerpt": excerpt[:220],
                }

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(fetch, missing))

    out = []
    for ref in references:
        did = data_id_from(ref)
        info = store.get(did) if did else None
        if (not info or not info.get("source")) and did:
            # Phase 8: cached entries from the prewarm carry only the item
            # name (often text_<hash>) — durable provenance outranks them.
            durable = _durable_reference(dataset, did)
            if durable and durable.get("source"):
                store[did] = durable
                info = durable
        if info and info.get("source"):
            entry = {"source": info["source"],
                     "excerpt": info["excerpt"],
                     "raw": str(ref)}
            # Only a durable row knows WHICH version this was read from; the
            # fingerprint path cannot, and guessing is the bug being closed.
            if info.get("document_version_id"):
                entry["document_version_id"] = info["document_version_id"]
            out.append(entry)
        else:
            # Include the string so the panel is never empty, but mark it as
            # unresolved rather than pretending it is a source.
            out.append({"source": None, "excerpt": None, "raw": str(ref)})
    return out


def data_id_for(dataset: str, filename: str) -> str | None:
    """Reverse of the resolve map: which data item holds this filename?

    Lets the app read an uploaded document back from the tenant, since uploads
    are not on local disk. Returns None rather than guessing.
    """
    for data_id, info in for_dataset(dataset).items():
        if info.get("source") == filename:
            return data_id
    return None
