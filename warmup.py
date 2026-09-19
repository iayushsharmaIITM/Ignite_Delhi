"""Pre-demo warm-up and rehearsal.

Run this ~15 minutes before judging. It exists because GATE 3 in the plan is
"warm every server and task", and that must be one command, not a checklist you
remember at the wrong moment.

It:
  1. checks /health and every upstream component
  2. runs every suggested demo question and times it
  3. verifies each answer carries citations
  4. reports anything that would embarrass you on stage

    python warmup.py            # against http://127.0.0.1:8000
    python warmup.py --base https://your-app.onrender.com
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

QUESTIONS = [
    "Why is the Bluepeak renewal at risk, and what have we promised them?",
    "What service credit do we owe Bluepeak, and who approved it?",
    "Who owns the Bluepeak renewal, and who owns the root cause analysis?",
    "Is the Bluepeak renewal date consistent across our documents?",
]

SLOW = 35.0  # seconds; above this, warn — a judge will notice the wait


def get(path, timeout=60):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as res:
        return res.status, res.read().decode()


def ask(question, timeout=180):
    url = BASE + "/api/ask?q=" + urllib.parse.quote(question)
    text, refs, errored = "", [], None
    with urllib.request.urlopen(url, timeout=timeout) as res:
        for raw in res:
            line = raw.decode().strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("type") == "chunk":
                text += ev.get("text", "")
            elif ev.get("type") == "references":
                refs = ev.get("items", [])
            elif ev.get("stage") == "error":
                errored = ev.get("message")
    return text.strip(), refs, errored


def main():
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    BASE = args.base.rstrip("/")

    print(f"Warm-up against {BASE}\n")
    problems = []

    # 1. health ------------------------------------------------------------
    print("[1/3] Health")
    try:
        _, body = get("/health", timeout=30)
        h = json.loads(body)
        print(f"      provider={h.get('provider')}  upstream={h.get('upstream', 'n/a')}  "
              f"auth={h.get('auth', 'n/a')}")
        for name, state in (h.get("components") or {}).items():
            flag = "ok " if state == "healthy" else "!! "
            print(f"      {flag}{name}: {state}")
            if state != "healthy":
                problems.append(f"upstream component {name} is {state}")
        if h.get("auth") == "failed":
            problems.append("API key rejected: " + str(h.get("auth_error"))[:120])
        if h.get("upstream") == "unreachable":
            problems.append("tenant instance unreachable: " + str(h.get("upstream_error"))[:120])
    except Exception as exc:  # noqa: BLE001
        problems.append(f"/health failed: {exc}")
        print(f"      FAILED: {exc}")

    # 2. graph -------------------------------------------------------------
    print("\n[2/3] Graph")
    try:
        _, body = get("/api/stats", timeout=120)
        s = json.loads(body)
        if s.get("ok"):
            print(f"      {s['nodes']} nodes, {s['edges']} edges (dataset: {s.get('dataset')})")
            if not s.get("nodes"):
                problems.append("graph is empty — run `python ingest.py`")
        else:
            problems.append("stats failed: " + str(s.get("error"))[:120])
            print(f"      FAILED: {s.get('error')}")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"/api/stats failed: {exc}")
        print(f"      FAILED: {exc}")

    # 3. every demo question ----------------------------------------------
    print(f"\n[3/3] Rehearsing {len(QUESTIONS)} demo questions")
    for i, q in enumerate(QUESTIONS, 1):
        t0 = time.time()
        try:
            text, refs, errored = ask(q)
            dt = time.time() - t0
            if errored:
                problems.append(f"Q{i} returned an error: {errored[:100]}")
                print(f"      Q{i}  ERROR  {dt:.1f}s  {errored[:80]}")
                continue
            slow = "  (SLOW)" if dt > SLOW else ""
            # Citations are the real proof of grounding; the length floor only
            # catches an empty answer. Q3 asks "who owns X" and legitimately
            # returns ~80 chars — a higher floor would raise a FALSE alarm
            # minutes before judging, which is worse than no alarm at all.
            ok = len(text) > 20 and refs
            if not ok:
                problems.append(f"Q{i} weak answer: {len(text)} chars, {len(refs)} citations")
            print(f"      Q{i}  {'ok ' if ok else '!! '} {dt:5.1f}s  "
                  f"{len(text):5d} chars  {len(refs)} citations{slow}")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"Q{i} threw: {exc}")
            print(f"      Q{i}  FAILED: {exc}")

    # verdict --------------------------------------------------------------
    print()
    if problems:
        print(f"{len(problems)} PROBLEM(S) — fix these before the demo:")
        for p in problems:
            print(f"  - {p}")
        print("\nIf they cannot be fixed in time, run with PROVIDER=mock.")
        sys.exit(1)

    print("All green. The demo path is warm and rehearsed.")


if __name__ == "__main__":
    main()
