"""Query battery — find which questions the demo brain answers reliably.

Non-destructive: read-only recall calls. Touches no data.
Purpose: we only put questions in the demo that are PROVEN to return a grounded,
cited answer. This replaces hope with measurement.

    python battery.py
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"
DATASET = "company_brain"

# Broad coverage of the corpus: single-doc lookups, cross-doc joins,
# contradictions, ownership, and deliberately unanswerable controls.
QUESTIONS = [
    # --- contract / fees ---
    "What is the annual fee and monthly recurring charge for Bluepeak?",
    "What is the notice period for non-renewal?",
    "What uptime commitment did we make, and what is the service credit if we miss it?",
    "What is the aggregate cap on service credits per contract year?",
    # --- incident ---
    "What caused the July outage and how long did it last?",
    "Who was the on-call engineer for the July incident?",
    "What was July's measured uptime and did it breach the commitment?",
    # --- credit / approval (the multi-hop family) ---
    "What service credit did we promise Bluepeak and who has to approve it?",
    "Does the promised credit breach our approval policy?",
    "What percentage credit needs CFO sign-off?",
    "Has the credit approval paperwork been closed out?",
    # --- ownership ---
    "Who owns the Bluepeak renewal?",
    "Who owns the root cause analysis?",
    "Who owns credit approval?",
    # --- dates / contradictions ---
    "Is the renewal date consistent across our documents?",
    "When does the contract expire?",
    "What is the renewal target date?",
    # --- other accounts (breadth) ---
    "What is the Fernwood onboarding issue?",
    "What does the on-call handbook say about rollback authority?",
    "What is the acknowledgement target for a P1?",
    # --- controls: should be refused or hedged ---
    "Who is the CEO of Bluepeak?",
    "What is our marketing budget?",
]


def ask(question: str, timeout: int = 200):
    url = BASE + "/api/ask?" + urllib.parse.urlencode({"q": question, "dataset": DATASET})
    text, refs, err = "", [], None
    t0 = time.time()
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
                err = ev.get("message")
    return text.strip(), refs, err, time.time() - t0


def main() -> int:
    print(f"Battery against {BASE}  dataset={DATASET}")
    print(f"{len(QUESTIONS)} questions\n")
    rows = []
    for i, q in enumerate(QUESTIONS, 1):
        try:
            text, refs, err, dt = ask(q)
        except Exception as exc:  # noqa: BLE001
            print(f"{i:>2}. THREW  {q[:60]}")
            rows.append((q, 0, 0, 0, "threw"))
            continue

        # A demo-safe answer: non-trivial prose AND at least one citation.
        #
        # NOTE ON THE LENGTH FLOOR: an earlier version used 60 chars and flagged
        # three CORRECT answers as weak - "Who owns the Bluepeak renewal?" is
        # legitimately 39 chars ("**Bluepeak renewal owner:** Marcus Lee."). A
        # short answer that is right is a good answer. The floor only exists to
        # catch an empty or truncated response, so it sits low; citations do the
        # real work of proving the answer is grounded.
        if err:
            verdict = "ERROR"
        elif not refs:
            verdict = "NO-CITE"
        elif len(text) < 25:
            verdict = "EMPTY"
        else:
            verdict = "OK"

        rows.append((q, len(text), len(refs), dt, verdict))
        print(f"{i:>2}. {verdict:<8} {dt:5.1f}s  {len(text):>5}ch  {len(refs)} cites  {q[:56]}")

    print()
    ok = [r for r in rows if r[4] == "OK"]
    print(f"demo-safe: {len(ok)}/{len(rows)}")
    weak = [r for r in rows if r[4] != "OK"]
    if weak:
        print("\nNOT demo-safe:")
        for q, n, c, dt, v in weak:
            print(f"  {v:<8} {n:>5}ch {c} cites  {q}")

    # The controls matter more than the average. The last two questions ask for
    # facts the corpus does not contain. A grounded system must say so; a
    # hallucinating one invents an answer. Print their replies verbatim so the
    # refusal is auditable rather than asserted.
    print("\n--- controls (corpus cannot answer these; refusal is the pass) ---")
    for q in QUESTIONS[-2:]:
        try:
            text, refs, err, dt = ask(q)
            first = text.strip().splitlines()[0] if text.strip() else "(empty)"
            print(f"  {q}\n    -> {first[:120]}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {q}\n    -> THREW {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
