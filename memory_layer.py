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
    url = os.getenv("COGNEE_SERVICE_URL") or ""
    # H10: loopback OSS runs auth-off (M0.2: both flags false), so no key is
    # needed — and requiring one silently served FIXTURES for a correctly
    # configured keyless setup, contradicting ingest.py's loopback rule.
    # Explicit PROVIDER still wins either way; a missing key against a REMOTE
    # url still falls back to mock.
    if url.startswith(("http://localhost", "http://127.0.0.1")):
        return True
    return bool(url and os.getenv("COGNEE_API_KEY"))


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


# Social REPLIES (the bot's own greetings/acknowledgements) — these are
# generated without retrieval, so any stored citations on them are stale.
_SOCIAL_REPLY_RE = re.compile(
    r"^\s*(?:h+i+|hello+|hey+|yo+|hiya|good\s*(?:morning|afternoon|evening)|"
    r"thanks?+(?:\s+you)?|you'?re\s*welcome|"
    r"i'?m\s*(?:doing\s*)?(?:good|great|fine|well|okay|ok)|"
    r"hi\s+there|i'?m\s*here\s*to\s*help|how\s*can\s*i\s*help\s*you|"
    r"just\s*let\s*me\s*know|happy\s*to\s*help)"
    r".*[!.?]*\s*$",
    re.IGNORECASE)


def _is_social_reply(text: str) -> bool:
    """True for the bot's own short greetings/acknowledgements — never
    document-grounded, so stored citations on them are stale by definition."""
    t = (text or "").strip()
    return bool(t) and len(t.split()) <= 15 and bool(_SOCIAL_REPLY_RE.match(t))


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
            # COR-1: track ANSWER TEXT, not events. The orchestrator emits a
            # stage step before any retrieval — counting every event as
            # "produced" took the mid-answer branch (and skipped the fixture
            # fallback) for failures that streamed zero answer text.
            if event.get("type") == "chunk" and (event.get("text") or "").strip():
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
        # COR-10: the UI contract is enriched {source, excerpt} objects
        # (citations.enrich) — bare strings were dropped by the client's
        # `i.source` filter, so mock mode showed no usable chips. Shape them
        # the same way: "chunk 1 of <file> — <excerpt>".
        shaped = []
        for ref in entry["references"]:
            if isinstance(ref, dict):
                shaped.append(ref)
                continue
            text = str(ref)
            m = re.match(r"chunk\s+\d+\s+of\s+(.+?)\s+[—–-]\s*(.*)$", text)
            if m:
                shaped.append({"source": m.group(1).strip(),
                               "excerpt": m.group(2).strip() or text,
                               "raw": text})
            else:
                shaped.append({"source": None, "excerpt": text, "raw": text})
        yield {"type": "references", "items": shaped}


# Greetings and social chitchat: the graph has nothing to say about them, so
# they are answered WITHOUT citations rather than dressing up unrelated
# chunks as evidence. COR-6: classification is token-vocabulary based, not
# substring based. The old regex lists were simultaneously too loose (bare
# content words like "team"/"today" matched SMALLTALK and skipped retrieval)
# and too tight ("thank you so much", "namaste" paid a 25s retrieval).
# Rules: (1) exact match against known social phrases; else (2) every token
# in the social vocabulary AND at least one core social token AND <= 8 words.
# A bare content word ("team", "today", "doc") has no core token by
# construction, so it can never misroute to smalltalk.
_CORE = frozenset({
    "hi", "hello", "hey", "yo", "hiya", "sup", "namaste", "hola",
    "thanks", "thank", "thx", "ty",
    "bye", "goodbye", "welcome", "sorry",
    "morning", "afternoon", "evening", "night",
    "awesome", "nice", "cool", "great", "perfect",
})
_FILLER = frozenset({
    "there", "you", "u", "my", "friend", "friends", "everyone", "folks",
    "guys", "all", "so", "much", "very", "really", "a", "lot", "ok", "okay",
    "good", "buenos", "dias", "job", "work", "stuff",
    "how", "are", "is", "r", "what", "up", "s", "it", "going", "do", "does",
})
_SOCIAL_PHRASES = frozenset({
    "how are you", "how r u", "how is it going", "hows it going",
    "how do you do", "what is up", "whats up", "what's up",
    "who are you", "what can you do", "what do you do",
    "good morning", "good afternoon", "good evening", "good night",
    "good day", "thank you", "see you", "see ya", "buenos dias",
    "good job", "good work", "great job", "great work", "nice work",
    "well done",
})


def _is_smalltalk(query: str) -> bool:
    """True for greetings and social chitchat that the documents cannot
    answer. Word-capped so a real question never misroutes."""
    q = (query or "").strip().lower()
    if not q:
        return False
    words = q.split()
    if len(words) > 8:
        return False
    squashed = re.sub(r"[^a-z\s]", "", q)
    squashed = re.sub(r"\s+", " ", squashed).strip()
    # Elongated greetings ("hii", "hellooo") — collapse 3+ runs, never 2
    # ("cool", "good" keep their double letters).
    squashed = re.sub(r"(.)\1{2,}", r"\1", squashed)
    # Doubled-letter greetings ("hii", "heyy") that the collapse above keeps:
    # match the greeting cores with flexible tails before token rules run.
    if re.fullmatch(r"(h+i+|hello+|hey+|yo+|hiya+|sup+)", squashed):
        return True
    if squashed in _SOCIAL_PHRASES:
        return True
    tokens = squashed.split()
    if not tokens:
        return False
    return (any(t in _CORE for t in tokens)
            and all(t in _CORE or t in _FILLER for t in tokens))


def _backend_dataset_name(slug: str | None) -> str | None:
    """The active generation's backend dataset name for a v2-created brain
    (slug stays the user-facing handle). Returns None for legacy brains —
    their tenant dataset IS the slug."""
    if not slug:
        return None
    try:
        from storage import DATABASE_URL
        import psycopg
        with psycopg.connect(DATABASE_URL, row_factory=psycopg.rows.dict_row) as conn, \
                conn.cursor() as cur:
            row = cur.execute(
                """select g.backend_dataset_name from brains b
                   join brain_generations g on g.id = b.active_generation_id
                   where b.slug = %s and b.deleted_at is null""", (slug,)).fetchone()
            return row["backend_dataset_name"] if row else None
    except Exception:  # noqa: BLE001 - resolution failure falls back to the slug
        return None


async def _cloud(query: str, dataset: str | None = None,
                 smalltalk: bool | None = None):
    """Real path, delegated to the orchestrator (head agent).

    The orchestrator runs retrieval racers and the citations prewarmer
    concurrently and yields the same event shapes this function used to —
    including the working-log steps the UI renders. Smalltalk detection stays
    here (it decides references-off before anything is delegated).
    """
    import orchestrator

    # Phase 8 (PR-7 read path): a v2-created brain's tenant dataset is named
    # backend-side (slug_<brainid>), not by slug. Resolve once here so the
    # orchestrator, racers and citation enrichment all target the real dataset.
    dataset = _backend_dataset_name(dataset) or dataset

    # app.py passes the RAW-question flag down: the wrapped query carries
    # context preamble that defeats the greeting regex in ongoing chats
    if smalltalk is None:
        smalltalk = _is_smalltalk(query)
    async for event in orchestrator.answer(query, dataset, smalltalk=smalltalk):
        yield event


