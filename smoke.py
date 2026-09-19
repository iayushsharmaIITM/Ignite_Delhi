"""Smoke test for the demo path. Run this after every slice.

Checks exactly the path a judge will walk: server up -> graph built -> answer
streams -> citations arrive. It is the only safety net a solo builder gets.

    python smoke.py
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"
QUESTION = "Why is the Bluepeak renewal at risk, and what have we promised them?"
FAILURES = []


def check(name, fn):
    try:
        fn()
        print(f"  PASS  {name}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(name)
        print(f"  FAIL  {name}: {exc}")


def get(path, timeout=180):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as res:
        return res.status, res.read().decode()


def health():
    status, body = get("/health", timeout=30)
    assert status == 200, f"status {status}"
    data = json.loads(body)
    assert data.get("ok") is True, "ok is not true"
    if data.get("provider") == "cloud":
        assert data.get("upstream") == "healthy", f"upstream={data.get('upstream')}"
        # The tenant /health endpoint is unauthenticated, so upstream=healthy
        # does NOT prove our key works. Check the authenticated probe too.
        assert data.get("auth") == "ok", (
            f"authenticated probe did not pass (auth={data.get('auth')!r}, "
            f"error={data.get('auth_error')})"
        )
    print(f"        provider={data.get('provider')} upstream={data.get('upstream')} "
          f"auth={data.get('auth', 'n/a')}")


def graph_has_nodes():
    _, body = get("/api/stats", timeout=120)
    data = json.loads(body)
    assert data.get("ok"), f"stats failed: {data}"
    assert data.get("nodes", 0) > 0, "graph is empty — run `python ingest.py` first"
    print(f"        {data['nodes']} nodes, {data['edges']} edges")


def graph_page():
    status, _ = get("/graph", timeout=30)
    assert status == 200, f"status {status}"


def answer_streams_with_citations():
    q = urllib.parse.quote(QUESTION)
    with urllib.request.urlopen(f"{BASE}/api/ask?q={q}", timeout=300) as res:
        lines = [ln for ln in res.read().decode().splitlines() if ln.strip()]

    events = [json.loads(ln) for ln in lines]
    text = "".join(e.get("text", "") for e in events if e.get("type") == "chunk")
    refs = next((e["items"] for e in events if e.get("type") == "references"), [])

    assert not any(e.get("stage") == "error" for e in events), "stream reported an error"
    assert any(e.get("stage") == "done" for e in events), "stream did not complete"
    assert len(text) > 80, f"answer too short ({len(text)} chars)"
    assert refs, "no citations returned — the answer is ungrounded"
    print(f"        {len(text)} chars, {len(refs)} sources")


if __name__ == "__main__":
    # --base so the same check can verify a deliberately broken local server
    # (does it actually fail?) and the deployed Render URL (does it work there?).
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    BASE = ap.parse_args().base.rstrip("/")

    print(f"Smoke test — demo path against {BASE}\n")
    check("GET /health returns 200 and upstream is healthy", health)
    check("graph has nodes", graph_has_nodes)
    check("GET /graph returns 200", graph_page)
    check("GET /api/ask streams an answer with citations", answer_streams_with_citations)

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        sys.exit(1)
    print("\nAll good. Demo path works.")
