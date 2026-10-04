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
import re
import time

RACERS = [
    ("graph retrieval agent", "GRAPH_COMPLETION"),
    ("vector retrieval agent", "RAG_COMPLETION"),
]

import llm  # shared endpoint resolution (Token Harbor primary, OpenRouter fallback)


async def answer(query: str, dataset: str | None, smalltalk: bool = False,
                 phatic_kind: str | None = None, lang: str | None = None,
                 tz: str | None = None):
    """Yield the same event stream memory_layer._cloud yields.

    The head agent's plan: prewarm citations while the retrieval racers run;
    first good answer wins; citations then resolve from warm caches.
    """
    import cognee_cloud

    t_start = time.time()

    # --- Fastest path: a social message answered from the table ----------------
    # Greetings, thanks, farewells and "what can you do" get fixed wording in the
    # reader's own UI language, with no model call and no retrieval at all. This is
    # strictly cheaper than the smalltalk route below, which still paid one small
    # completion for the same messages, and it is the path the shipping app never
    # reached: the web tier used to classify the question AFTER prepending its
    # local-time note, so every greeting looked like content and fell through to
    # retrieval. See tests/test_phatic.py.
    if phatic_kind:
        import phatic
        reply = phatic.reply(phatic_kind, lang, tz=tz)
        if reply:
            yield {"stage": "step", "label": "Phatic: template, no model, no retrieval"}
            for word in reply.split(" "):
                yield {"type": "chunk", "text": word + " "}
                await asyncio.sleep(0.01)
            yield {"stage": "done", "ms": int((time.time() - t_start) * 1000)}
            return

    # --- Fast path: greetings/smalltalk never touch the brain ----------------
    # Retrieval (embed + graph search + generation) is an 11-25s round trip;
    # a greeting needs none of it. One small direct completion instead.
    if smalltalk:
        yield {"stage": "step", "label": "Smalltalk: direct chat, no retrieval"}
        reply = await asyncio.to_thread(_direct_chat, query)
        for word in reply.split(" "):
            yield {"type": "chunk", "text": word + " "}
            await asyncio.sleep(0.01)
        yield {"stage": "done", "ms": int((time.time() - t_start) * 1000)}
        return

    # --- Sub-agent: citations prewarmer (overlaps everything) ----------------
    prewarm = asyncio.ensure_future(_prewarm(dataset))
    yield {"stage": "step", "label": "Orchestrator: planning retrieval agents"}

    race = os.getenv("KESTREL_RACE_RETRIEVAL", "1") != "0"

    if not race:
        name, strategy = RACERS[0]
        yield {"stage": "step", "label": f"Delegating to {name}"}
        t0 = time.time()
        # COR-3: recall takes 5 params — the old 6-positional call raised
        # TypeError on every ask with the race disabled.
        results = await asyncio.to_thread(
            cognee_cloud.recall, query, dataset, strategy)
        yield {"stage": "step", "label": f"{name} returned",
               "ms": int((time.time() - t0) * 1000)}
    else:
        # --- Sub-agents: retrieval racers, simultaneously ---------------------
        # H3, honestly: cancelling a to_thread await does NOT stop the worker
        # thread — both recalls run to completion and both burn tokens. The
        # p.cancel() below only detaches the loser so the winner streams
        # sooner; the race trades ~2x retrieval tokens for first-answer
        # latency. Cost-saving lever: KESTREL_RACE_RETRIEVAL=0 runs a single
        # GRAPH_COMPLETION retrieval instead (no double spend, slower tail).
        # --- Retrieval: hedged, not raced --------------------------------
        # Cost decision (owner): full speed at 1x cost. The old design started
        # BOTH strategies at once and paid double on every ask (cancelling a
        # to_thread await never stops the worker thread — the "loser" always
        # ran to completion). Now GRAPH runs first; RAG starts ONLY if GRAPH
        # is slow past the hedge delay or fails fast. Typical ask: 1x cost,
        # same latency. Slow tail: RAG covers it, occasional 2x. Levers:
        # KESTREL_HEDGE_SECONDS (default 8); KESTREL_RACE_RETRIEVAL=0 keeps
        # the old single-retrieval path above.
        hedge = float(os.getenv("KESTREL_HEDGE_SECONDS", "8"))
        primary, secondary = RACERS[0], RACERS[1]
        tasks = {
            asyncio.ensure_future(
                asyncio.to_thread(cognee_cloud.recall, query, dataset, primary[1])
            ): primary[0],
        }
        yield {"stage": "step",
               "label": f"Delegating to {primary[0]} (hedged backup ready)"}
        t0 = time.time()

        # --- Router sub-agent: runs concurrently with the racers. If it says
        # CHAT, the racers are cancelled and the answer bypasses retrieval —
        # general conversation never pays the 10-25s brain round trip.
        router_task = asyncio.ensure_future(asyncio.to_thread(_classify, query))
        done_r, _ = await asyncio.wait({router_task}, timeout=8)
        route = "brain"
        if router_task in done_r and not router_task.exception():
            route = router_task.result()
        yield {"stage": "step",
               "label": ("Router: general chat — bypassing retrieval agents"
                         if route == "chat" else
                         "Router: document question — retrieval agents continue")}
        if route == "chat":
            for p in tasks:
                p.cancel()
                asyncio.ensure_future(_swallow(p))
            # The citations prewarmer was already running. Cancelling the racers and
            # returning without it left that task detached: a general-chat reply,
            # which retrieves nothing, still fanned out a full document dump against
            # the brain service on an 8-worker pool, delaying citations for every
            # concurrent ask in the process. The normal exit awaits it (below); this
            # branch must not be the one place that forgets.
            prewarm.cancel()
            asyncio.ensure_future(_swallow(prewarm))
            reply = await asyncio.to_thread(_direct_chat_general, query)
            for word in reply.split(" "):
                yield {"type": "chunk", "text": word + " "}
                await asyncio.sleep(0.01)
            yield {"stage": "done", "ms": int((time.time() - t_start) * 1000)}
            return

        results = None
        winner = None
        pending = set(tasks)
        hedged = False
        answered_blank = False    # a racer that completed with no answer text
        errored = 0               # a racer that actually failed
        while pending:
            # The hedge: wait for the primary only up to the delay. A fast
            # failure skips the wait entirely (fail over at once); a slow
            # primary earns a backup racer after `hedge` seconds.
            timeout = None if hedged else hedge
            done, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED, timeout=timeout)
            if not done and not hedged:
                hedged = True
                fut = asyncio.ensure_future(
                    asyncio.to_thread(
                        cognee_cloud.recall, query, dataset, secondary[1]))
                tasks[fut] = secondary[0]
                pending.add(fut)
                yield {"stage": "step",
                       "label": f"{primary[0]} slow — hedging with {secondary[0]}"}
                continue
            for fut in done:
                name = tasks[fut]
                try:
                    res = fut.result()
                    text = cognee_cloud.answer_text(res)
                    if not text.strip():
                        answered_blank = True
                    if text.strip() and results is None:
                        results, winner = res, name
                        yield {"stage": "step",
                               "label": f"{name} answered first",
                               "ms": int((time.time() - t0) * 1000)}
                except Exception as exc:  # noqa: BLE001 - a failed retrieval is not a failed ask
                    errored += 1
                    yield {"stage": "step",
                           "label": f"{name} failed ({str(exc)[:60]})"}
                    if not hedged:
                        # Fail fast: the primary is dead, start the backup now
                        # instead of waiting out the hedge delay.
                        hedged = True
                        fut2 = asyncio.ensure_future(
                            asyncio.to_thread(
                                cognee_cloud.recall, query, dataset, secondary[1]))
                        tasks[fut2] = secondary[0]
                        pending.add(fut2)
                finally:
                    if results is not None:
                        for p in pending:
                            p.cancel()
                        # await cancellations quietly so nothing leaks
                        for p in pending:
                            asyncio.ensure_future(_swallow(p))
                        pending = set()
        if results is None and answered_blank and errored == 0:
            # Nothing came back, but nothing failed either: the brain answered the
            # question by saying nothing. Reporting that as an outage used to fall
            # through to memory_layer's fixture safety net, which answered with a
            # committed paragraph about the DEMO brain and hand-written citation
            # chips naming real contracts — a fabricated citation for a question the
            # brain did answer. Say the truth instead: no finding, no sources.
            yield {"stage": "step", "label": "Retrieval returned no content"}
            for word in ("I found nothing in this brain that answers that. I only "
                         "say what your documents say, so there is no source to "
                         "cite here — try rephrasing, or add the document that "
                         "would cover it. ").split(" "):
                yield {"type": "chunk", "text": word + " "}
            yield {"stage": "done", "ms": int((time.time() - t_start) * 1000)}
            return
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
            # COR-5: never re-type the demo name — one constant, one import.
            asyncio.to_thread(citations.enrich, items, dataset or cognee_cloud.dataset()))

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
        # COR-4: citations are an optional enrichment — their failure must
        # never fail the stream. The answer already went out with `done`; a
        # refs lookup that blows up here used to append a false
        # "connection dropped mid-answer" trailer to a COMPLETE answer.
        try:
            enriched = await refs_task
        except Exception:  # noqa: BLE001 - answer stands, chips just absent
            enriched = []
        if enriched:
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


_PURE_GREETING_RE = re.compile(
    r"^\s*(h+i+|hello+|hey+|yo+|hiya|good\s*(morning|afternoon|evening))"
    r"[\s!.?]*$", re.IGNORECASE)


ROUTER_INSTRUCTION = (
    "You are the router of a company-brain application. The company's documents "
    "cover contracts, tickets, meetings, policies, projects, people and finances. "
    "Decide whether the user's message should be answered FROM those documents, or "
    "is general conversation (time, date, weather, greetings, opinions, jokes, "
    "general knowledge, math). If it might relate to the company's documents or "
    "business, answer BRAIN. Only answer CHAT when it is clearly general "
    "conversation. Questions about the brain itself — 'what is this brain "
    "about', 'what documents do you have', 'summarize these documents', "
    "'what is this specific brain about' — are ALWAYS BRAIN: they can only be "
    "answered from the indexed documents. Reply with exactly one word: BRAIN or CHAT."
)


def _classify(query: str) -> str:
    """Router sub-agent: BRAIN or CHAT. Defaults to BRAIN on any failure —
    a misroute to retrieval costs seconds; a misroute to chat costs trust."""
    import requests

    import observe  # P5 observability (fail-open)

    t0 = time.time()
    key = llm.api_key()
    if not key:
        return "brain"
    try:
        resp = requests.post(
            llm.chat_url(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": os.getenv("ROUTER_MODEL", llm.default_model()),
                "messages": [
                    {"role": "system", "content": ROUTER_INSTRUCTION},
                    {"role": "user", "content": query[-2000:]},
                ],
                "max_tokens": 200,
            },
            timeout=45,
        )
        resp.raise_for_status()
        word = (resp.json()["choices"][0]["message"].get("content") or "").strip().upper()
        # COR-7: the reply must BE the token, not merely contain it — a
        # negation ("not a chat request") contains CHAT and flipped the route,
        # silently skipping retrieval for a real question.
        first = word.split()[0] if word.split() else ""
        route = "chat" if first == "CHAT" else "brain"
        observe.trace(
            feature="router", route=route, model=os.getenv("ROUTER_MODEL", llm.default_model()),
            est_prompt=len(query[-2000:]) // 4, est_completion=len(word) // 4,
            ms=int((time.time() - t0) * 1000), ok=True,
        )
        return route   # BRAIN, or anything ambiguous: the safe default
    except Exception as exc:  # noqa: BLE001 - router down: retrieval is the safe default
        observe.trace(
            feature="router", route="brain", model=os.getenv("ROUTER_MODEL", llm.default_model()),
            ms=int((time.time() - t0) * 1000), ok=False, error=str(exc)[:200],
        )
        return "brain"


def _direct_chat_general(query: str) -> str:
    """General conversation: no retrieval context, but time-aware."""
    import requests
    from datetime import datetime

    key = llm.api_key()
    if not key:
        return "I can answer questions about your company's documents — try me on those."
    try:
        now = datetime.now().strftime("%A, %d %B %Y, %H:%M local time")
        resp = requests.post(
            llm.chat_url(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": os.getenv("SUMMARIZER_MODEL", llm.default_model()),
                "messages": [
                    {"role": "system",
                     "content": "You are Kestrel, a company brain. This message is "
                                "general conversation, not a document question — answer "
                                "helpfully in a sentence or two. Current local time: " + now},
                    {"role": "user", "content": query},
                ],
                "max_tokens": 250,
            },
            timeout=45,
        )
        resp.raise_for_status()
        return (resp.json()["choices"][0]["message"].get("content")
                or "Try me on your company documents.").strip()
    except Exception:  # noqa: BLE001
        return "I can answer questions about your company's documents — try me on those."


def _direct_chat(query: str) -> str:
    """Small completion for greetings — no retrieval, no citations.

    Pure greetings (just the word) get an instant template — a network round
    trip to say \"hello\" is waste. Anything chatty goes to the LLM."""
    # ongoing chats wrap the question in context: judge the LAST line only
    tail = query.strip().splitlines()[-1] if query.strip() else query
    tail = re.sub(r"^follow-up question:\s*", "", tail.strip(), flags=re.IGNORECASE)
    if _PURE_GREETING_RE.match(tail):
        query = tail
        hour = time.localtime().tm_hour
        part = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
        return (f"Good {part}! Ask me anything about your company's documents — "
                "I answer with cited sources from your contracts, tickets and meetings.")
    import requests

    key = llm.api_key()
    if not key:
        return "Hello! Ask me anything about your company documents."
    try:
        resp = requests.post(
            llm.chat_url(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": os.getenv("SUMMARIZER_MODEL", llm.default_model()),
                "messages": [
                    {"role": "system",
                     "content": "You are Kestrel, a company brain that answers from the "
                                "user's documents. The user is just greeting or chatting — "
                                "respond warmly in one or two sentences and suggest what "
                                "you can do: answer questions grounded in their documents "
                                "with cited sources."},
                    {"role": "user", "content": query},
                ],
                "max_tokens": 150,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return (resp.json()["choices"][0]["message"].get("content")
                or "Hello! How can I help?").strip()
    except Exception:  # noqa: BLE001 - greeting must never fail
        return "Hello! Ask me anything about your company documents."


async def _swallow(task: asyncio.Task):
    """Await a cancelled task without propagating (keeps the loop clean)."""
    try:
        await task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass
