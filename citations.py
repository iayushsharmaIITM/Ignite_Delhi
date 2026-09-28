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
UPLOADS = os.path.join(HERE, "fixtures", "uploads.json")

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


def _fingerprint(text: str, length: int = 120) -> str:
    """A whitespace-insensitive prefix, for matching raw content to a corpus file."""
    return re.sub(r"\s+", " ", text or "").strip().lower()[:length]


def _corpus_fingerprints() -> dict[str, str]:
    """{fingerprint: filename} for every file in corpus/."""
    out = {}
    if not os.path.isdir(CORPUS):
        return out
    for name in sorted(os.listdir(CORPUS)):
        path = os.path.join(CORPUS, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                out[_fingerprint(handle.read())] = name
        except OSError:
            continue
    return out


def _upload_fingerprints(dataset: str) -> dict[str, str]:
    """{fingerprint: filename} for files uploaded into this brain."""
    try:
        with open(UPLOADS, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in (manifest.get(dataset) or {}).items()}


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
                key = f"{dataset}::{fp[:32]}"
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

    # Two sources of truth for "which filename is this?":
    #   corpus/        - the pre-built demo documents
    #   uploads.json   - files a user uploaded, recorded at upload time
    # Content is the join key for both, because the tenant does not let us set a
    # document's name (it accepts a `filename` field and silently ignores it).
    corpus = _corpus_fingerprints()
    corpus.update(_upload_fingerprints(dataset))
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
            "source": named or corpus.get(_fingerprint(raw)),
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
    corpus = _corpus_fingerprints()
    corpus.update(_upload_fingerprints(dataset))

    def fetch(did):
        try:
            raw = cognee_cloud.data_raw(dataset_id, did)
        except Exception:  # noqa: BLE001
            raw = None
        excerpt = re.sub(r"\s+", " ", raw or "").strip()
        named = (items_map.get(did) or "").strip()
        named = None if _GENERATED_NAME_RE.match(named) else (named or None)
        store[did] = {
            "source": named or corpus.get(_fingerprint(raw)),
            "excerpt": excerpt[:220],
        }

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(fetch, missing))


def data_id_from(reference) -> str | None:
    """Pull a data_id out of a Cognee evidence string."""
    match = _DATA_ID_RE.search(str(reference))
    return match.group(1) if match else None


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
            corpus = _corpus_fingerprints()
            corpus.update(_upload_fingerprints(dataset))

            def fetch(did):
                try:
                    raw = cognee_cloud.data_raw(dataset_id, did)
                except Exception:  # noqa: BLE001 - a missing raw must not break the answer
                    raw = None
                excerpt = re.sub(r"\s+", " ", raw or "").strip()
                named = (items_map.get(did) or "").strip()
                named = None if _GENERATED_NAME_RE.match(named) else (named or None)
                store[did] = {
                    "source": named or corpus.get(_fingerprint(raw)),
                    "excerpt": excerpt[:220],
                }

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(fetch, missing))

    out = []
    for ref in references:
        did = data_id_from(ref)
        info = store.get(did) if did else None
        if info and info.get("source"):
            out.append(
                {
                    "source": info["source"],
                    "excerpt": info["excerpt"],
                    "raw": str(ref),
                }
            )
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
