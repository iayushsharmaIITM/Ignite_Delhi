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

import os
import re
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "corpus")

# How long a resolved map stays warm. The tenant only changes when something is
# ingested, and this saves a round trip per question.
_TTL_SECONDS = 300

_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()

# "chunk 1 of document text_abc (data_id: xyz, chunk_id: 123)"
_DATA_ID_RE = re.compile(r"data_id:\s*([0-9a-fA-F-]{8,})")


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


def _fetch_map(dataset: str) -> dict:
    """{data_id: {"source": filename|None, "excerpt": str}} for one dataset."""
    import cognee_cloud

    corpus = _corpus_fingerprints()
    resolved: dict = {}

    dataset_id = cognee_cloud.resolve_id(dataset)
    items = cognee_cloud.data_items(dataset_id)

    for item in items:
        data_id = item.get("id")
        if not data_id:
            continue
        try:
            raw = cognee_cloud.data_raw(dataset_id, data_id)
        except Exception:  # noqa: BLE001 - a missing raw must not break the answer
            continue

        excerpt = re.sub(r"\s+", " ", raw or "").strip()
        resolved[data_id] = {
            # None is an honest answer: we would rather show no filename than a
            # wrong one.
            "source": corpus.get(_fingerprint(raw)),
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
        resolved = {}
    with _lock:
        _cache[dataset] = (now, resolved)
    return resolved


def data_id_from(reference) -> str | None:
    """Pull a data_id out of a Cognee evidence string."""
    match = _DATA_ID_RE.search(str(reference))
    return match.group(1) if match else None


def enrich(references: list, dataset: str) -> list:
    """Attach source + excerpt to each evidence string.

    Returns a list of dicts so the UI can render a filename and a quote instead
    of a UUID. Falls back to the raw string when nothing can be resolved.
    """
    if not references:
        return []
    mapping = for_dataset(dataset)

    out = []
    for ref in references:
        text = str(ref)
        data_id = data_id_from(text)
        found = mapping.get(data_id) if data_id else None
        if found:
            out.append(
                {
                    "source": found["source"],
                    "excerpt": found["excerpt"],
                    "raw": text,
                }
            )
        else:
            # Include the string so the panel is never empty, but mark it as
            # unresolved rather than pretending it is a source.
            out.append({"source": None, "excerpt": None, "raw": text})
    return out
