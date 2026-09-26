"""Orchestrator: the head agent that delegates an ask to parallel sub-agents.

WHY THIS FILE EXISTS
--------------------
A question used to be one blocking call: recall(GRAPH_COMPLETION) → stream →
resolve citations. Everything waited on everything. The single call was also
the single point of failure — one slow or failed strategy meant a slow or
failed answer.

The orchestrator plans the ask as three CONCURRENT sub-agents:

    Head agent (this file)
      ├─ Retrieval racer A: recall(GRAPH_COMPLETION)   — multi-hop graph + LLM
      ├─ Retrieval racer B: recall(RAG_COMPLETION)     — vector retrieval + LLM
      └─ Citations prewarmer: dataset id + data items  — so enrich() is instant

The racers run simultaneously; the FIRST non-empty answer wins and the loser
is cancelled. The prewarmer overlaps both, so by the time the answer exists,
citation resolution is a cache lookup. Every delegation and completion is
yielded as a `stage:"step"` event — the UI's working log narrates what the
head agent is doing, with real durations, exactly like an agent worklog.

Event contract (identical to memory_layer's, so /api/ask is unchanged):
    {"stage": "step", "label": str, "ms": int}
    {"type": "chunk", "text": str}
    {"type": "references", "items": [...]}

Set KESTREL_RACE_RETRIEVAL=0 to run single-strategy (one tenant generation
per question instead of two).
"""

from __future__ import annotations

import asyncio
import os
import time

RACERS = [
    ("graph retrieval agent", "GRAPH_COMPLETION"),
    ("vector retrieval agent", "RAG_COMPLETION"),
]


async def answer(query: str, dataset: str | None, smalltalk: bool = False):
    """Yield the same event stream memory_layer._cloud yields.

    The head agent's plan: prewarm citations while the retrieval racers run;
    first good answer wins; citations then resolve from warm caches.
    """
    import cognee_cloud

    t_start = time.time()

    # --- Sub-agent: citations prewarmer (overlaps everything) ----------------
    prewarm = asyncio.ensure_future(_prewarm(dataset))
    yield {"stage": "step", "label": "Orchestrator: planning retrieval agents"}

    race = os.getenv("KESTREL_RACE_RETRIEVAL", "1") != "0"

    if smalltalk or not race:
        name, strategy = RACERS[0]
        yield {"stage": "step", "label": f"Delegating to {name}"}
        t0 = time.time()
        results = await asyncio.to_thread(
            cognee_cloud.recall, query, dataset, strategy if not smalltalk else None,
            None, None, not smalltalk)
        yield {"stage": "step", "label": f"{name} returned",
               "ms": int((time.time() - t0) * 1000)}
    else:
        # --- Sub-agents: retrieval racers, simultaneously ---------------------
        tasks = {
            asyncio.ensure_future(
                asyncio.to_thread(cognee_cloud.recall, query, dataset, strategy)
            ): name
            for name, strategy in RACERS
        }
        yield {"stage": "step",
               "label": f"Delegating to {len(tasks)} retrieval agents simultaneously"}
        t0 = time.time()

        results = None
        winner = None
        pending = set(tasks)
        while pending:
            done, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED)
            for fut in done:
                name = tasks[fut]
                try:
                    res = fut.result()
                    text = cognee_cloud.answer_text(res)
                    if text.strip() and results is None:
                        results, winner = res, name
                        yield {"stage": "step",
                               "label": f"{name} answered first",
                               "ms": int((time.time() - t0) * 1000)}
                except Exception as exc:  # noqa: BLE001 - a failed racer is not a failed ask
                    yield {"stage": "step",
                           "label": f"{name} failed ({str(exc)[:60]})"}
                finally:
                    if results is not None:
                        for p in pending:
                            p.cancel()
                        # await cancellations quietly so nothing leaks
                        for p in pending:
                            asyncio.ensure_future(_swallow(p))
                        pending = set()
        if results is None:
            raise RuntimeError("both retrieval agents failed")
        if winner != RACERS[0][0]:
            yield {"stage": "step", "label": f"Using {winner}'s answer"}

    # --- Head agent: stream the winning answer --------------------------------
    raw = cognee_cloud.answer_text(results)
    answer_text, evidence = cognee_cloud.split_evidence(raw)

    items = [] if smalltalk else (cognee_cloud.references(results) or evidence)
    refs_task = None
    if items:
        import citations

        yield {"stage": "step", "label": f"Citations agent: resolving {len(items)} references"}
        rt0 = time.time()
        refs_task = asyncio.ensure_future(
            asyncio.to_thread(citations.enrich, items, dataset or "company_brain"))

    # stream the prose without artificial pacing — the answer already exists;
    # every ms of sleep here is a ms the user waits for text they could read
    words = answer_text.split(" ")
    for i in range(0, len(words), 3):
        yield {"type": "chunk", "text": " ".join(words[i:i + 3]) + " "}
        await asyncio.sleep(0.01)

    # The answer is the deliverable — mark it done NOW. Citations resolve
    # concurrently (they were started before the stream) and arrive as a
    # trailing event; the UI renders them on arrival without blocking.
    yield {"stage": "done", "ms": int((time.time() - t_start) * 1000)}

    if refs_task is not None:
        enriched = await refs_task
        grounded = sum(1 for e in enriched if e.get("source"))
        yield {"stage": "step", "label": f"Grounded in {grounded} sources",
               "ms": int((time.time() - rt0) * 1000)}
        yield {"type": "references", "items": enriched}

    await prewarm  # never raises (internally guarded)


async def _prewarm(dataset: str | None):
    """Resolve the dataset id + item names now, so enrich() never has to."""
    try:
        import citations
        import cognee_cloud

        target = dataset or cognee_cloud.dataset()
        await asyncio.to_thread(citations.prewarm, target)
    except Exception:  # noqa: BLE001 - prewarming is best-effort by design
        pass


async def _swallow(task: asyncio.Task):
    """Await a cancelled task without propagating (keeps the loop clean)."""
    try:
        await task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass
