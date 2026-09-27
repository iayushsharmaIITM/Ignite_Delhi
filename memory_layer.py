"""Memory layer: one interface, two implementations.

This is the single most valuable file in the skeleton. It exists so that a
broken API, a dead network, or a rate limit can never kill your demo.

    PROVIDER=mock    -> no network, no API key, instant. Your demo safety net.
    PROVIDER=cloud   -> real remember/recall against the Cognee Cloud tenant.

Never call Cognee directly from the UI. Go through this file.

The event contract (so the UI can render citations, not just text):

    {"type": "chunk",      "text": "..."}
    {"type": "references", "items": [...]}
"""

import asyncio
import json
import os
import re
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures", "answers.json")

# Load .env BEFORE reading any config below.
#
# This module resolves PROVIDER at import time, so whichever module imports it
# first wins. A Render Workflow task imports memory_layer lazily inside the task
# body — i.e. potentially before anything has loaded .env — which would silently
# resolve PROVIDER to "mock" and quietly serve fixtures from a deployed
# workflow. Loading here removes that entire class of bug.
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(HERE, ".env"))
except ImportError:
    pass


def _cloud_configured() -> bool:
    """Cheap check that avoids importing requests on the mock path."""
    return bool(os.getenv("COGNEE_SERVICE_URL") and os.getenv("COGNEE_API_KEY"))


# Explicit PROVIDER wins. Otherwise prefer cloud when it is fully configured,
# and fall back to the offline fixtures so a missing key is never fatal.
PROVIDER = os.getenv("PROVIDER") or ("cloud" if _cloud_configured() else "mock")


async def remember(text: str, dataset: str | None = None,
                   filename: str | None = None) -> None:
    """Store text as memory. Builds the knowledge graph under the hood.

    `dataset=None` targets COGNEE_DATASET. Pass an explicit name to exercise a
    scratch dataset without touching the demo graph.

    `filename` becomes the stored document's name, so later evidence can cite
    the file the user actually uploaded instead of `text_<hash>`.
    """
    if PROVIDER == "mock":
        return
    import cognee_cloud

    await asyncio.to_thread(cognee_cloud.remember, text, dataset, None, True, filename)


def default_dataset() -> str:
    """The pre-built demo brain. Everything else is a user-created brain."""
    return os.getenv("COGNEE_DATASET", "company_brain")


async def recall(query: str, dataset: str | None = None,
                 smalltalk: bool | None = None):
    """Yield events. Async generator so the UI can stream.

    `dataset=None` asks the demo brain. Any other value asks that specific
    brain, which is what makes one UI able to serve every uploaded brain.
    """
    if PROVIDER == "mock":
        async for event in _mock(query, dataset):
            yield event
        return

    # Cloud first. If the tenant is unreachable, fall back to the committed
    # answers rather than leaving the user with an error - a dead tenant must
    # not make the demo look broken. The mock refuses for an uploaded brain,
    # which is the honest outcome there: we have no answers for documents the
    # fixtures never saw.
    produced = False
    try:
        async for event in _cloud(query, dataset, smalltalk=smalltalk):
            produced = True
            yield event
        return                      # clean finish - the real answer stands alone
    except Exception as exc:  # noqa: BLE001
        if produced:
            # H3: part of a real answer has already been streamed. Falling
            # through to the fixtures would emit ONE response that mixes a real
            # answer with a committed one - worse than either alone, and
            # impossible for the reader to tell apart. Report and stop.
            yield {
                "type": "chunk",
                "text": f"\n\n_(The connection dropped mid-answer: {str(exc)[:80]}. "
                        "The answer above is incomplete.)_",
            }
            return
        yield {
            "type": "chunk",
            "text": f"(The knowledge graph is unreachable - {str(exc)[:80]}. "
                    "Falling back to the committed answers.)\n\n",
        }

    # Only reached when nothing was produced: a clean fallback to the fixtures.
    async for event in _mock(query, dataset):
        yield event


async def _mock(query: str, dataset: str | None = None):
    """Offline path. Reads a committed fixture, so it works with zero network.

    The fixtures only describe the demo brain. Serving them for an uploaded
    brain would be a fabricated answer dressed as a real one, so we refuse
    instead - the same reason app.py refuses to show the demo graph for a
    user's brain.
    """
    if dataset and dataset != default_dataset():
        yield {
            "type": "chunk",
            "text": (
                f"The offline safety net only covers the demo brain, so it has "
                f"no answers for '{dataset}'. Run with PROVIDER=cloud to query "
                "an uploaded brain."
            ),
        }
        return

    try:
        with open(FIXTURES) as handle:
            fixtures = json.load(handle)
    except FileNotFoundError:
        yield {"type": "chunk", "text": "No fixtures/answers.json found."}
        return

    entry = fixtures.get(query) or fixtures.get("default") or {}
    if isinstance(entry, str):
        entry = {"answer": entry}

    for word in (entry.get("answer") or "No fixture for that query.").split(" "):
        yield {"type": "chunk", "text": word + " "}
        await asyncio.sleep(0.02)  # makes streaming visible in the demo

    if entry.get("references"):
        yield {"type": "references", "items": entry["references"]}


# Greetings and meta questions: the graph has nothing to say about them, so
# they are answered WITHOUT citations rather than dressing up unrelated
# chunks as evidence.
_SMALLTALK_RE = re.compile(
    r"^\s*(h+i+|hello+|hey+|yo+|sup|hiya|good\s*(morning|afternoon|evening)|"
    r"thanks?+(\s+you)?|ty|what'?s\s*up|whats\s*up|how\s*(are|r)\s*(you|u)|"
    r"who\s*(are|r)\s*(you|u)|what\s*can\s*(you|u)\s*do|help\s*me?|test)\s*[!.?]*\s*$",
    re.IGNORECASE)


def _is_smalltalk(query: str) -> bool:
    q = (query or "").strip()
    return bool(q) and len(q.split()) <= 4 and bool(_SMALLTALK_RE.match(q))


async def _cloud(query: str, dataset: str | None = None,
                 smalltalk: bool | None = None):
    """Real path, delegated to the orchestrator (head agent).

    The orchestrator runs retrieval racers and the citations prewarmer
    concurrently and yields the same event shapes this function used to —
    including the working-log steps the UI renders. Smalltalk detection stays
    here (it decides references-off before anything is delegated).
    """
    import orchestrator

    # app.py passes the RAW-question flag down: the wrapped query carries
    # context preamble that defeats the greeting regex in ongoing chats
    if smalltalk is None:
        smalltalk = _is_smalltalk(query)
    async for event in orchestrator.answer(query, dataset, smalltalk=smalltalk):
        yield event


