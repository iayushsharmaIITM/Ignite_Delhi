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
                 smalltalk: bool | None = None, phatic_kind: str | None = None,
                 lang: str | None = None, tz: str | None = None):
    """Yield events. Async generator so the UI can stream.

    `dataset=None` asks the demo brain. Any other value asks that specific
    brain, which is what makes one UI able to serve every uploaded brain.

    `phatic_kind` is the family name of a social message (greeting, thanks, …)
    decided by the web tier on the caller's own words; `smalltalk` stays the boolean
    every existing caller passes, and is derived from the kind when not given. `lang`
    only chooses the wording of a phatic reply — never what is retrieved.
    """
    if phatic_kind is None:
        # A caller that only passes the boolean (or neither) still gets the correct
        # family: derive it rather than guessing, because "thanks" answered with a
        # good-morning line is its own kind of wrong.
        phatic_kind = _phatic_family(query) if smalltalk is not False else None
    if PROVIDER == "mock":
        async for event in _mock(query, dataset, phatic_kind=phatic_kind, lang=lang, tz=tz):
            yield event
        return

    # Cloud first. If the tenant is unreachable, fall back to the committed
    # answers rather than leaving the user with an error - a dead tenant must
    # not make the demo look broken. The mock refuses for an uploaded brain,
    # which is the honest outcome there: we have no answers for documents the
    # fixtures never saw.
    produced = False
    try:
        async for event in _cloud(query, dataset, smalltalk=smalltalk,
                                  phatic_kind=phatic_kind, lang=lang, tz=tz):
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


async def _mock(query: str, dataset: str | None = None, phatic_kind: str | None = None,
                lang: str | None = None, tz: str | None = None):
    """Offline path. Reads a committed fixture, so it works with zero network.

    The fixtures only describe the demo brain. Serving them for an uploaded
    brain would be a fabricated answer dressed as a real one, so we refuse
    instead - the same reason app.py refuses to show the demo graph for a
    user's brain.

    A phatic message is answered from the template here too, BEFORE any fixture is
    read. Without this the offline mode answered "hi" with a committed paragraph about
    Bluepeak renewals and its citations attached — a fabricated citation for a
    greeting, and the exact thing the product's invariant forbids. It also meant the
    battery (which runs PROVIDER=mock) could never observe the phatic route at all.
    """
    if phatic_kind:
        import phatic as _phatic
        reply = _phatic.reply(phatic_kind, lang, tz=tz)
        if reply:
            yield {"stage": "step", "label": "Phatic: template, no model, no retrieval"}
            for word in reply.split(" "):
                yield {"type": "chunk", "text": word + " "}
            yield {"stage": "done", "refs": [], "ms": 0}
            return
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

# Which family a social message belongs to, so the reply can be chosen without a
# model. Order matters in `_PHATIC_CORES`: the first family holding a token in the
# message wins, so "thanks hello" reads as thanks, matching what a person means
# when they start with it.
#
# `phatic.KINDS` is the authority for the names. A family listed here but missing
# there would silently fall through to retrieval, which the test tier checks.
_PHATIC_PHRASES = {
    "how are you": "howareyou", "how r u": "howareyou",
    "how is it going": "howareyou", "hows it going": "howareyou",
    "how do you do": "howareyou", "what is up": "howareyou",
    "whats up": "howareyou", "what s up": "howareyou",
    "who are you": "capability", "what can you do": "capability",
    "what do you do": "capability", "how do you work": "capability",
    "what are you": "capability", "who r u": "capability",
    "good morning": "greeting", "good afternoon": "greeting",
    "good evening": "greeting", "good night": "farewell", "good day": "greeting",
    "buenos dias": "greeting",
    "thank you": "thanks", "thanku": "thanks", "thanks a lot": "thanks",
    "see you": "farewell", "see ya": "farewell", "see you later": "farewell",
    "good job": "praise", "good work": "praise", "great job": "praise",
    "great work": "praise", "nice work": "praise", "well done": "praise",
    "nice one": "praise", "good bot": "praise",
    "you re welcome": "welcome", "your welcome": "welcome",
    "no problem": "welcome", "no worries": "welcome", "it s ok": "welcome",
    "its ok": "welcome", "that s ok": "welcome", "thats ok": "welcome",
    "sorry": "sorry", "so sorry": "sorry", "my bad": "sorry",
    "excuse me": "sorry",
}

# Families whose words can stand alone as the whole message. `_CORE` stays the union,
# because other code and tests read it as the social vocabulary.
_PHATIC_CORES = (
    ("greeting", {"hi", "hello", "hey", "yo", "hiya", "sup", "namaste", "hola",
                  "morning", "afternoon", "evening", "heythere"}),
    ("thanks", {"thanks", "thank", "thx", "ty"}),
    ("welcome", {"welcome"}),
    ("farewell", {"bye", "goodbye"}),
    ("sorry", {"sorry"}),
    ("praise", {"awesome", "nice", "cool", "great", "perfect"}),
)

_CORE = frozenset(w for _, words in _PHATIC_CORES for w in words)


def phatic_kind(query: str) -> str | None:
    """Which social family this message is, or None if it may be a real question.

    None is the safe answer and the common one: anything that is not unmistakably
    phatic goes to the brain. The word cap and the all-tokens rule exist for that
    reason (COR-6), and they are kept exactly as they were — this function only adds
    the family name, plus one fix that changes everything in production:

    The ask route prepends the caller's browser timezone to the text before the model
    sees it, so "what time is it?" can be answered. That note used to be added BEFORE
    classification ran, which meant the shipping app's "hi" arrived here as
    "client local time asiakolkata hi", failed the all-tokens rule, and paid a full
    11-25s retrieval round trip to be greeted. Detection is now blind to the note, and
    app.py classifies the user's own message before attaching anything.
    """
    import phatic as _phatic

    q = _phatic.strip_system_note(query)
    q = (q or "").strip().lower()
    if not q:
        return None
    words = q.split()
    if len(words) > 8:
        return None
    squashed = re.sub(r"[^a-z\s]", "", q)
    squashed = re.sub(r"\s+", " ", squashed).strip()
    # Elongated greetings ("hii", "hellooo") — collapse 3+ runs, never 2
    # ("cool", "good" keep their double letters).
    squashed = re.sub(r"(.)\1{2,}", r"\1", squashed)
    if not squashed:
        return None
    # Doubled-letter greetings ("hii", "heyy") that the collapse above keeps:
    # match the greeting cores with flexible tails before token rules run.
    if re.fullmatch(r"(h+i+|hello+|hey+|yo+|hiya+|sup+)", squashed):
        return "greeting"
    if squashed in _PHATIC_PHRASES:
        return _PHATIC_PHRASES[squashed]
    tokens = squashed.split()
    if not tokens:
        return None
    if not any(t in _CORE for t in tokens):
        return None
    if not all(t in _CORE or t in _FILLER for t in tokens):
        return None
    for t in tokens:
        for kind, words_of_kind in _PHATIC_CORES:
            if t in words_of_kind:
                return kind
    return "greeting"


# A stable alias for the classifier, because `recall` below takes a parameter named
# `phatic_kind`. A function reached through its own shadowed name resolves to a string
# at call time — a TypeError that would surface only on the exact path that passes no
# family, which is the worst kind of latent break to leave in a greeting handler.
_phatic_family = phatic_kind


def _is_smalltalk(query: str) -> bool:
    """True for greetings and social chitchat that the documents cannot answer.

    Kept as the boolean every existing caller already uses; `phatic_kind` is the same
    decision with the family attached, so a reply can be chosen without a model call.
    Word-capped so a real question never misroutes.
    """
    return phatic_kind(query) is not None


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
                 smalltalk: bool | None = None, phatic_kind: str | None = None,
                 lang: str | None = None, tz: str | None = None):
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

    # app.py passes the RAW-question family down: the wrapped query carries
    # context preamble that defeats the greeting regex in ongoing chats
    if phatic_kind is None and smalltalk is None:
        phatic_kind = _phatic_family(query)
    async for event in orchestrator.answer(query, dataset, smalltalk=bool(smalltalk),
                                          phatic_kind=phatic_kind, lang=lang, tz=tz):
        yield event


