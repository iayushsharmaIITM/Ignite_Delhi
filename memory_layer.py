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


async def remember(text: str, dataset: str | None = None) -> None:
    """Store text as memory. Builds the knowledge graph under the hood.

    `dataset=None` targets COGNEE_DATASET. Pass an explicit name to exercise a
    scratch dataset without touching the demo graph.
    """
    if PROVIDER == "mock":
        return
    import cognee_cloud

    await asyncio.to_thread(cognee_cloud.remember, text, dataset)


def default_dataset() -> str:
    """The pre-built demo brain. Everything else is a user-created brain."""
    return os.getenv("COGNEE_DATASET", "company_brain")


async def recall(query: str, dataset: str | None = None):
    """Yield events. Async generator so the UI can stream.

    `dataset=None` asks the demo brain. Any other value asks that specific
    brain, which is what makes one UI able to serve every uploaded brain.
    """
    if PROVIDER == "mock":
        async for event in _mock(query, dataset):
            yield event
        return
    async for event in _cloud(query, dataset):
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


async def _cloud(query: str, dataset: str | None = None):
    """Real path: the Cognee Cloud tenant does the graph work.

    `asyncio.to_thread` keeps the FastAPI event loop free while the blocking
    HTTP call runs — the answer arrives, then we stream it word by word so the
    UI feels alive even though the model answered in one shot.
    """
    import cognee_cloud

    # Second positional arg is `name` — the dataset to query.
    results = await asyncio.to_thread(cognee_cloud.recall, query, dataset)

    # Cognee returns the evidence block inline in the answer text, so split it
    # out and stream only the prose. The citations get their own panel.
    raw = cognee_cloud.answer_text(results)
    answer, evidence = cognee_cloud.split_evidence(raw)

    for word in answer.split(" "):
        yield {"type": "chunk", "text": word + " "}
        await asyncio.sleep(0.012)

    items = cognee_cloud.references(results) or evidence
    if items:
        yield {"type": "references", "items": items}
