"""Render Workflow tasks. This is the orchestration tier.

THE RULE THAT MATTERS: each task run gets its own EPHEMERAL container, which is
destroyed when the run ends. So durable state must live outside the container.

We learned this the hard way. Cognee's default graph backend is file-based
(ladybug), so a graph built during an `ingest` run was gone by the time a
`retrieve` run started. The fix is not to avoid ephemeral containers — it is to
put the graph somewhere containers cannot kill. Here that is the Cognee Cloud
tenant instance, addressed over HTTP.

That is also why this tier holds no credentials beyond COGNEE_API_KEY:
no LLM key, no database password, no mounted volume, no shared filesystem.

Run locally:  render workflows dev -- python pipeline.py
Trigger:      render workflows tasks runs start answer --local --input='{"query": "hi"}'
"""

import asyncio

from render import Retry, TaskContext, Workflows

app = Workflows()


# --------------------------------------------------------------------------
# ingest — one task run per document, fanned out in parallel
# --------------------------------------------------------------------------

@app.task(
    retry=Retry(max_retries=3, wait_duration_ms=1000, backoff_scaling=1.5),
    timeout_seconds=600,
)
async def ingest_document(ctx: TaskContext, text: str, dataset: str = "") -> str:
    """Ingest a single document. Runs in its own container.

    `dataset` defaults to COGNEE_DATASET; pass a name to target a scratch
    dataset, which is how the fan-out below is tested without touching the
    demo graph.
    """
    from memory_layer import remember

    await remember(text, dataset or None)
    return "ingested"


@app.task(timeout_seconds=900)
async def ingest_corpus(ctx: TaskContext, documents: list, dataset: str = "") -> dict:
    """Fan ingestion out across containers — one task run per document.

    Each ctx.run() is its own ephemeral container. They share no filesystem and
    no memory; the only thing they have in common is the tenant instance they
    all write to. That is the scalability claim, and it is testable rather than
    rhetorical: add documents, get more containers, change nothing else.
    """
    # Guard, because the failure mode here is silent and nasty. Task inputs
    # arrive as JSON, so a caller can easily pass the whole request object where
    # a list is expected — and `for doc in documents` would then iterate the
    # DICT'S KEYS. We watched exactly that happen: it ingested the literal
    # strings "dataset" and "documents" and still returned
    # {"queued": 2, "failed": 0} — a confident success over garbage. Fail loudly.
    if not isinstance(documents, (list, tuple)):
        raise TypeError(
            f"documents must be a list of strings, got {type(documents).__name__}. "
            "Note the CLI spreads a bare JSON object as keyword arguments; wrapping "
            "it in an array passes the whole object as the first positional argument."
        )
    if not all(isinstance(d, str) and d.strip() for d in documents):
        raise ValueError("documents must contain only non-empty strings")

    results = await asyncio.gather(
        *(ctx.run(ingest_document, doc, dataset) for doc in documents),
        return_exceptions=True,
    )
    ok = sum(1 for r in results if not isinstance(r, Exception))
    return {"queued": ok, "failed": len(results) - ok}


# --------------------------------------------------------------------------
# retrieve + answer
# --------------------------------------------------------------------------

@app.task(timeout_seconds=300)
async def retrieve(ctx: TaskContext, query: str) -> dict:
    """Retrieve the answer and its evidence from memory."""
    from memory_layer import recall

    events = [event async for event in recall(query)]
    text = "".join(e.get("text", "") for e in events if e.get("type") == "chunk")
    refs = next((e["items"] for e in events if e.get("type") == "references"), [])
    return {"answer": text.strip(), "references": refs}


@app.task(timeout_seconds=600)
async def answer(ctx: TaskContext, query: str) -> str:
    """Chain a subtask run on its own compute, then return the answer.

    ctx.run() executes the subtask on separate compute. For parallel work:
        a, b = await asyncio.gather(ctx.run(t, x), ctx.run(t, y))
    """
    result = await ctx.run(retrieve, query)
    return result["answer"]


if __name__ == "__main__":
    app.start()
