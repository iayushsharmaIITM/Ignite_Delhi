"""Cognee Cloud client — the single place that talks to the tenant instance.

WHY THIS FILE EXISTS
--------------------
Cognee's local SDK needs a model-provider key AND a local graph store. Both are
state that must live *somewhere* — and "somewhere" cannot be a Render task run,
because task runs are ephemeral containers destroyed when the run ends.

The Cognee Cloud tenant instance is that "somewhere". It owns the LLM, the
embeddings, the vector store and the graph. So every ephemeral container needs
exactly one thing to do its job: this API key.

That is the whole architecture in one sentence, and it is why this file is
deliberately dependency-light (`requests` only, no Cognee SDK import).

    POST /api/v1/remember             multipart, raw_data=<text>
    GET  /api/v1/datasets/status      poll until the graph is built
    POST /api/v1/recall               json, query + includeReferences
    GET  /api/v1/datasets/{id}/graph  the graph view

TRAPS BAKED INTO THIS FILE (each cost real debugging time)
----------------------------------------------------------
1. `dataset` / `dataset_ids` query params take a **UUID**, not a name.
   Passing a name returns 422 uuid_parsing. Hence `resolve_id()`.
2. The terminal pipeline state is `DATASET_PROCESSING_COMPLETED`. An exact
   match on '"completed"' never fires, so the poll loops until timeout.
   Hence `is_terminal()`.
3. Calling recall() before the graph finishes building returns a confident,
   WRONG answer. We measured it: it invented "$39 per year" for a $420,000
   contract. Hence `wait_ready()`.
4. Config read at import time is a footgun — a caller that loads .env after
   importing this module silently gets empty strings. Hence every accessor
   reads the environment lazily, and `load_env()` runs on import.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Iterable, Optional

import requests

DEFAULT_DATASET = "company_brain"

# SearchType values we actually use. See Cognee's SearchType enum.
GRAPH_COMPLETION = "GRAPH_COMPLETION"
TEMPORAL = "TEMPORAL"
RAG_COMPLETION = "RAG_COMPLETION"

# Terminal pipeline states. Live value: "DATASET_PROCESSING_COMPLETED".
_TERMINAL = ("completed", "success", "errored", "failed")

_ENV_LOADED = False


class CogneeCloudError(RuntimeError):
    """Raised when the tenant instance refuses or fails a call."""


# --------------------------------------------------------------------------
# configuration (lazy on purpose — see trap 4)
# --------------------------------------------------------------------------

def load_env(path: Optional[str] = None) -> None:
    """Load .env once, if python-dotenv is available.

    Existing environment variables always win: load_dotenv does not override
    by default, so an explicit `PROVIDER=cloud python app.py` still works.
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(path)


def service_url() -> str:
    return os.getenv("COGNEE_SERVICE_URL", "").rstrip("/")


def api_key() -> str:
    return os.getenv("COGNEE_API_KEY", "")


def dataset() -> str:
    return os.getenv("COGNEE_DATASET", DEFAULT_DATASET)


def timeout() -> int:
    return int(os.getenv("COGNEE_TIMEOUT", "600"))


def configured() -> bool:
    """True when both the service URL and key are present."""
    return bool(service_url() and api_key())


def _headers() -> dict:
    return {"X-Api-Key": api_key()}


def _base() -> str:
    url = service_url()
    if not url:
        raise CogneeCloudError(
            "COGNEE_SERVICE_URL is not set. Discover it with:\n"
            "  curl -H \"X-Api-Key: $COGNEE_API_KEY\" "
            "https://api.aws.cognee.ai/api/tenants/current/service-url"
        )
    return url


# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------

def _check(resp: requests.Response, what: str) -> None:
    if resp.status_code >= 400:
        raise CogneeCloudError(f"{what} failed: HTTP {resp.status_code} — {resp.text[:300]}")


def _is_uuid(value: str) -> bool:
    return len(value) == 36 and value.count("-") == 4


def is_terminal(state: Any) -> bool:
    """True when a pipeline status payload has reached a terminal state.

    Public because the web tier streams ingestion progress and needs to know
    when to stop polling without duplicating the terminal-state list.
    """
    blob = json.dumps(state).lower()
    return any(word in blob for word in _TERMINAL)


load_env()


# --------------------------------------------------------------------------
# health + datasets
# --------------------------------------------------------------------------

def health() -> dict:
    """Tenant instance health. Used by /health so the demo never looks dead."""
    resp = requests.get(f"{_base()}/health", timeout=30)
    _check(resp, "health")
    return resp.json()


def datasets() -> list:
    resp = requests.get(f"{_base()}/api/v1/datasets/", headers=_headers(), timeout=60)
    _check(resp, "datasets")
    return resp.json()


def dataset_id(name: Optional[str] = None) -> Optional[str]:
    name = name or dataset()
    for d in datasets():
        if d.get("name") == name:
            return d.get("id")
    return None


def resolve_id(name: Optional[str] = None) -> str:
    """Accept either a dataset name or a UUID and return a UUID.

    TRAP 1: id-taking endpoints want a UUID. Passing a name yields
    `422 uuid_parsing: ... found 'p' at 1`. Callers can just use the name.
    """
    name = name or dataset()
    if _is_uuid(name):
        return name
    found = dataset_id(name)
    if not found:
        raise CogneeCloudError(f"Dataset {name!r} not found")
    return found


def exists(name: str) -> bool:
    """True when a dataset with this name is present on the tenant."""
    return dataset_id(name) is not None


def delete_dataset(name: str) -> bool:
    """Delete an entire dataset. Returns False if it was not there.

    The guard is deliberate and belongs in code, not in a comment: this project
    has already polluted the demo graph once, and the cheapest possible way to
    lose the demo would be a cleanup script that removes the wrong brain.
    """
    if name == dataset():
        raise CogneeCloudError(
            f"refusing to delete {name!r} - that is the demo dataset"
        )
    if not exists(name):
        return False
    resp = requests.delete(
        f"{_base()}/api/v1/datasets/{resolve_id(name)}",
        headers=_headers(),
        timeout=timeout(),
    )
    _check(resp, "delete_dataset")
    return True


# --------------------------------------------------------------------------
# write path
# --------------------------------------------------------------------------

def remember(text: str, name: Optional[str] = None, node_set: Optional[list] = None,
             run_in_background: bool = True) -> dict:
    """Ingest one document. Returns the pipeline status payload.

    `run_in_background=True` is what lets us fan ingestion out across parallel
    Render task runs — each container fires and forgets, and the graph lands in
    the tenant instance where the next container can see it.
    """
    data: dict[str, Any] = {"datasetName": name or dataset()}
    if run_in_background:
        data["run_in_background"] = "true"
    if node_set:
        data["node_set"] = node_set

    resp = requests.post(
        f"{_base()}/api/v1/remember",
        headers=_headers(),
        files={"raw_data": (None, text)},
        data=data,
        timeout=timeout(),
    )
    _check(resp, "remember")
    return resp.json()


def status(name: Optional[str] = None) -> dict:
    """Pipeline status for a dataset (name or UUID)."""
    resp = requests.get(
        f"{_base()}/api/v1/datasets/status",
        headers=_headers(),
        params={"dataset": resolve_id(name), "include_error_detail": "true"},
        timeout=60,
    )
    _check(resp, "status")
    return resp.json()


def wait_ready(name: Optional[str] = None, timeout_s: int = 900, interval: int = 6) -> dict:
    """Block until the dataset's pipeline reaches a terminal state.

    TRAP 3: querying mid-ingest returns a confident, wrong answer. Never ask a
    question of a graph you have not finished building.
    """
    key = resolve_id(name)
    deadline = time.time() + timeout_s
    last: Any = None
    while time.time() < deadline:
        state = status(key)
        if is_terminal(state):
            return state
        last = state
        time.sleep(interval)
    raise CogneeCloudError(f"Dataset {name!r} not ready after {timeout_s}s. Last: {last}")


# --------------------------------------------------------------------------
# read path
# --------------------------------------------------------------------------

def recall(query: str, name: Optional[str] = None, search_type: str = GRAPH_COMPLETION,
           top_k: Optional[int] = None, include_references: bool = True) -> list:
    """Ask the graph. Returns Cognee's result list (text + evidence)."""
    body: dict[str, Any] = {
        "query": query,
        "datasets": [name or dataset()],
        "searchType": search_type,
        "includeReferences": include_references,
    }
    if top_k:
        body["topK"] = top_k

    resp = requests.post(
        f"{_base()}/api/v1/recall", headers=_headers(), json=body, timeout=timeout()
    )
    _check(resp, "recall")
    payload = resp.json()
    return payload if isinstance(payload, list) else [payload]


def answer_text(results: Iterable) -> str:
    """Flatten recall results into the answer string."""
    parts = []
    for item in results:
        if isinstance(item, dict):
            parts.append(item.get("text") or str(item.get("raw") or ""))
        else:
            parts.append(str(item))
    return "\n".join(p for p in parts if p).strip()


def references(results: Iterable) -> list:
    """Pull structured citation blocks out of recall results, if present.

    In practice Cognee returns evidence inline in the answer text, so this is
    usually empty and `split_evidence` does the work. Kept because the API does
    expose `includeReferences` and the shape may change.
    """
    out = []
    for item in results:
        if not isinstance(item, dict):
            continue
        for key in ("references", "reference", "citations"):
            val = item.get(key)
            if val:
                out.extend(val if isinstance(val, list) else [val])
    return out


def split_evidence(text: str) -> tuple:
    """Separate the answer from Cognee's trailing "Evidence:" block.

    The graph-completion answer arrives as prose followed by:

        Evidence:
        - chunk 1 of document text_d689e237… (data_id: …, chunk_id: …)

    Rendering that as its own panel is the cheapest credibility win in the
    demo: it shows the answer is grounded in documents, not invented.
    """
    marker = "\nEvidence:"
    if marker not in text:
        return text.strip(), []

    answer, _, tail = text.partition(marker)
    lines = []
    for raw in tail.splitlines():
        line = raw.strip().lstrip("-").strip()
        if line:
            lines.append(line)
    return answer.strip(), lines


# --------------------------------------------------------------------------
# graph view
# --------------------------------------------------------------------------

def graph_summary(name: Optional[str] = None) -> dict:
    resp = requests.get(
        f"{_base()}/api/v1/datasets/graph-summary",
        headers=_headers(),
        params={"dataset_ids": resolve_id(name)},
        timeout=120,
    )
    _check(resp, "graph_summary")
    return resp.json()


def graph(name: Optional[str] = None, full: bool = True, limit: int = 500) -> dict:
    """The graph itself, for the graph view."""
    resp = requests.get(
        f"{_base()}/api/v1/datasets/{resolve_id(name)}/graph",
        headers=_headers(),
        params={"full": str(full).lower(), "max_nodes": limit},
        timeout=120,
    )
    _check(resp, "graph")
    return resp.json()
