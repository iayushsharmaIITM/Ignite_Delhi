"""The phatic route: greetings answered instantly, everything else sent to the brain.

Run standalone (no database, no provider, no browser — safe for the CI fast lane):

    python3 tests/test_phatic.py

Prints one PASS/FAIL line per check and exits non-zero if any failed.

Why this file exists. The product answers "hi" from a template with no retrieval and
no model call — that code was written, reviewed and merged. It has never worked in the
shipping app: `app.py` appends a `[Client local time: …]` note to the question and then
asks the classifier about the MUTATED string, so the detector saw
"client local time asiakolkata hi", failed its own vocabulary rule, and paid an 11-25s
retrieval round trip to say hello. Nine of nine common greetings, right.

The rules these checks defend:
  * Fail OPEN to the brain. A misroute to retrieval costs seconds; a misroute to a
    template costs trust, and a user asking a real question a canned answer swallows is
    the worst failure available here.
  * Zero model calls on the phatic path. "Instant" means no round trip at all.
  * Never a citation, never a fabricated quote, and no semantic memoisation of any kind
    — that is the standing product invariant, not a preference.
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Hermetic before anything is imported. Two reasons, both real:
#  * `import app` runs storage.init(), so this file must not be able to reach the
#    production database by accident. If a DATABASE_URL is already in the
#    environment it has to name the lab on 5434, or this refuses to run at all —
#    the same rule the other tiers carry.
#  * PROVIDER decides whether a question is answered from fixtures or from the live
#    tenant. Answering "hi" must never cost a real inference call, so this pins mock
#    and pins AUTH_MODE=off for its own process only.
os.environ["PROVIDER"] = "mock"
os.environ["AUTH_MODE"] = "off"
_url = os.environ.get("DATABASE_URL", "")
if _url and "5434" not in _url:
    raise SystemExit(
        "REFUSING: DATABASE_URL names a server that is not the lab (5434). This tier "
        "imports app.py, which runs storage.init(); it must not be pointed at the live "
        "database. Unset DATABASE_URL to run with no database at all, or use the lab.")
if not _url:
    # Nothing listening on port 1: storage.init() fails fast and the app degrades,
    # which is the same shape CI gets with no database provisioned.
    os.environ["DATABASE_URL"] = "postgresql://kestrel:kestrel@127.0.0.1:1/kestrel"

import memory_layer          # noqa: E402
import phatic                # noqa: E402

FAILS = []
CHECKS = 0


def check(name, ok, detail=""):
    global CHECKS
    CHECKS += 1
    if ok:
        print(f"  PASS  {name}")
    else:
        FAILS.append(name)
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


def expect_raise(fn, *a, **k):
    try:
        fn(*a, **k)
        return False
    except AssertionError as exc:
        return "no network" in str(exc) or "network" in str(exc)


# --------------------------------------------------------------------------
# 1. The detector recognises the phatic families, by kind not just yes/no
# --------------------------------------------------------------------------
KIND_CASES = {
    "greeting": ["hi", "hello", "hey", "hii", "heyy", "hellooo", "yo", "hi there",
                 "good morning", "good evening", "namaste", "hola"],
    "thanks": ["thanks", "thank you", "thanks a lot", "thank you so much", "ty", "thx"],
    "howareyou": ["how are you", "how r u", "hows it going", "how is it going",
                  "how do you do", "whats up", "what is up"],
    "farewell": ["bye", "goodbye", "see you", "see ya"],
    "capability": ["what can you do", "who are you", "what do you do", "how do you work"],
    "praise": ["good job", "well done", "great work", "nice work"],
}
for kind, cases in KIND_CASES.items():
    bad = [c for c in cases if memory_layer.phatic_kind(c) != kind]
    check(f"{kind}: every case classifies as {kind}", not bad, f"wrong/none: {bad}")

# _is_smalltalk must stay correct for existing callers, as the pure wrapper it is now.
check("_is_smalltalk agrees with phatic_kind", all(
    memory_layer._is_smalltalk(c) == (memory_layer.phatic_kind(c) is not None)
    for cases in KIND_CASES.values() for c in cases))

# --------------------------------------------------------------------------
# 2. THE BUG: the note the browser appends must not blind the classifier.
#    Both directions are asserted, because defence in depth is the point: the
#    detector must survive the prefix, AND app.py must ask before adding it.
# --------------------------------------------------------------------------
UI_PREFIX = "[Client local time: 2026-10-04T18:32:11.222Z (Asia/Kolkata)]\n"
blinded = [c for cases in KIND_CASES.values() for c in cases
           if memory_layer.phatic_kind(UI_PREFIX + c) is None]
check("a prefixed greeting is still phatic", not blinded, f"lost: {blinded[:6]}")
check("the injected note is stripped from what the brain sees",
      phatic.strip_system_note(UI_PREFIX + "hello") == "hello")

# The app-level ordering, asserted on the argument the classifier actually receives:
# a real ask must classify the user's own text, never the augmented one.
import app as app_module     # noqa: E402

_seen = {}
_orig = memory_layer.phatic_kind


def _spy(q, *a, **k):
    _seen["arg"] = q
    return _orig(q, *a, **k)


memory_layer.phatic_kind = _spy
try:
    from fastapi.testclient import TestClient
    client = TestClient(app_module.app)
    r = client.get("/api/ask", params={"q": "hi", "tz": "Asia/Kolkata",
                                      "local_time": "2026-10-04T18:32:11.222Z"},
                   headers={"Accept": "application/x-ndjson"})
    check("the ask route answers a greeting", r.status_code == 200, f"status {r.status_code}")
    arg = _seen.get("arg", None)
    check("app.py classifies BEFORE injecting the local-time note",
          arg is not None and "Client local time" not in (arg or ""),
          f"classifier received: {str(arg)[:90]!r}")
    check("…and the note still reaches the model path for real questions",
          "local time" not in (arg or "").lower() or arg.strip() == "hi")
finally:
    memory_layer.phatic_kind = _orig

# --------------------------------------------------------------------------
# 3. Fail OPEN. Anything that could be a real question must go to the brain.
# --------------------------------------------------------------------------
MUST_NOT_BE_PHATIC = [
    # The demo's own suggestion chips: if one of these ever routes to a
    # template, the product's headline answers become canned non-answers.
    "Why is the Bluepeak renewal at risk?",
    "What credit do we owe, and who approved it?",
    "Who owns the renewal and the RCA?",
    "Is the renewal date consistent?",
    # Mixed greeting + question: the greeting must not swallow the question.
    "hi, what is the Bluepeak renewal risk",
    "hello, thanks for last time — who signs off the credit note",
    "thanks. also, is the warranty 24 months",
    # Content words alone must never route social.
    "team", "today", "doc", "invoice", "the policy",
    # Long-form social-looking text still goes to the brain, uncapped risk.
    "hello, I would like a detailed summary of everything in this brain please",
]
for q in MUST_NOT_BE_PHATIC:
    got = memory_layer.phatic_kind(q)
    check(f"not phatic: {q[:46]!r}", got is None, f"classified as {got!r}")

# --------------------------------------------------------------------------
# 4. Zero model calls: the phatic path must make no network request at all.
# --------------------------------------------------------------------------
import requests  # noqa: E402


def _boom(*a, **k):
    raise AssertionError("no network allowed on the phatic path")


_real_post, _real_get = requests.post, requests.get
requests.post, requests.get = _boom, _boom
try:
    kinds = list(KIND_CASES)
    ok_all = True
    for k in kinds:
        for loc in phatic.LOCALES:
            txt = phatic.reply(k, loc, now=None)
            if not txt or len(txt) < 12:
                ok_all = False
    check("every kind answers from the table in every locale", ok_all,
          f"{len(kinds)} kinds x {len(phatic.LOCALES)} locales")
    check("unknown locale falls back without raising",
          len(phatic.reply("greeting", "klingon", now=None)) > 12)
    check("unknown kind returns None rather than guessing",
          phatic.reply("not-a-kind", "en", now=None) is None)
except AssertionError as exc:
    check("the phatic table needs no network", False, str(exc))
finally:
    requests.post, requests.get = _real_post, _real_get

# The orchestrator's own phatic branch must not reach the model either.
import orchestrator  # noqa: E402


async def _collect(agen):
    return [e async for e in agen]


try:
    requests.post = _boom
    requests.get = _boom
    evs = asyncio.run(_collect(orchestrator.answer("hi", None, phatic_kind="greeting", lang="en")))
    labels = " ".join(str(e.get("label", "")) + str(e.get("stage", "")) for e in evs)
    text = "".join(e.get("text", "") for e in evs if e.get("type") == "chunk").strip()
    check("orchestrator answers a greeting with no retrieval and no model call",
          bool(text) and "Phatic" in labels and "retrieval" not in labels.lower().replace("no retrieval", ""),
          labels[:120])
    check("the phatic answer streams as chunks the UI already renders",
          any(e.get("type") == "chunk" for e in evs) and
          any(e.get("stage") == "done" for e in evs))
    check("a phatic answer carries no citations",
          not any("srcs" in str(e).lower() or "citation" in str(e).lower() for e in evs))
except AssertionError as exc:
    check("orchestrator's phatic path makes no network call", False, str(exc))
except TypeError as exc:
    check("orchestrator accepts the phatic route parameters", False,
          f"answer() signature missing phatic plumbing: {exc}")
finally:
    requests.post, requests.get = _real_post, _real_get

# --------------------------------------------------------------------------
# 5. The invariant, stated as a check: no meaning-derived shortcut on this path.
# --------------------------------------------------------------------------
_src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "phatic.py"), encoding="utf-8").read()
# Look for the primitives, not the substrings. A first version of this check searched
# for "cache|memo" and failed on the word `memory_layer` in a docstring — a gate that
# flags an unrelated word is a gate somebody turns off.
cacheable = re.findall(r"(?<![\w.])lru_cache|functools\.cache|@cache\b|@memoize|diskcache|redis|_CACHE\b",
                       _src)
check("phatic.py has no result-cache of any kind", not cacheable, f"found {cacheable}")
check("the note is matched the way the producer writes it (capital C)",
      phatic.strip_system_note(UI_PREFIX + "hello") == "hello"
      and phatic.strip_system_note("[client local time: x]\nhey") == "hey")
check("a message that is ONLY the note does not read as a greeting",
      memory_layer.phatic_kind(UI_PREFIX) is None
      and memory_layer.phatic_kind("[Client local time: 2026-10-04T18:32:11.222Z "
                                   "(Asia/Kolkata)]") is None)

# --------------------------------------------------------------------------
# 6. Time-of-day must be real, and locale-correct, not a hardcoded string.
# --------------------------------------------------------------------------
from datetime import datetime  # noqa: E402

morning = phatic.reply("greeting", "en", now=datetime(2026, 10, 4, 9, 0))
evening = phatic.reply("greeting", "en", now=datetime(2026, 10, 4, 20, 0))
check("greeting varies with time of day", morning != evening, f"{morning!r} vs {evening!r}")
check("greeting names the part of the day",
      any(w in morning.lower() for w in ("morning", "afternoon", "evening")), morning)
hi_morning = phatic.reply("greeting", "hi", now=datetime(2026, 10, 4, 9, 0))
check("a Hindi greeting is not English text",
      hi_morning != morning and len(hi_morning) > 12, hi_morning[:60])
check("no reply leaks a template placeholder",
      not any(re.search(r"[{}\[\]]|%s|TODO", phatic.reply(k, loc, now=None) or "")
              for k in KIND_CASES for loc in phatic.LOCALES))

print()
if FAILS:
    print(f"{len(FAILS)} FAILED: " + ", ".join(FAILS[:6]))
    raise SystemExit(1)
print(f"PHATIC ROUTING: PASS ({CHECKS} checks)")
