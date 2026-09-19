"""Workflow-tier smoke test. Safe by construction.

WHY THIS FILE EXISTS
The web tier has `smoke.py`. The workflow tier had nothing — so verifying it meant
hand-typed `render workflows start` commands. One of those, an array-wrapped
`--input='[{...}]'`, silently made `ingest_corpus` iterate a dict's *keys* and
ingest the literal strings "dataset" and "documents". Because the subtasks then
received an empty dataset name, that junk landed in the **demo graph**
(219/500 -> 225/504) and had to be surgically removed.

This script exists so that cannot happen again:

  * it always targets a UNIQUE scratch dataset, never `COGNEE_DATASET`
  * it refuses to run at all if the scratch name would collide with the demo dataset
  * it deletes the scratch dataset in a `finally` block, even on failure
  * it serialises `--input` as a bare JSON object — the format the CLI spreads
    into keyword arguments

The one probe that touches the demo dataset is the chained `answer` task, which is
READ-ONLY (it queries, it does not ingest). That is deliberate: `retrieve` resolves
its dataset from `COGNEE_DATASET`, so chaining cannot be tested against a scratch
dataset without changing the task.

    render workflows dev -- python pipeline.py     # in another terminal
    python wf_smoke.py
    python wf_smoke.py --keep                      # leave the scratch dataset behind
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cognee_cloud as cc  # noqa: E402  (loads .env on import)

DEMO = cc.dataset()
SCRATCH = f"wf_probe_{int(time.time())}"
FAILURES = []


# --------------------------------------------------------------------------
# the render CLI
# --------------------------------------------------------------------------

def find_render() -> str:
    """Locate the render CLI. It is not always on PATH."""
    for cand in (
        shutil.which("render"),
        os.path.expanduser("~/.workbuddy-ai/bin/render"),
        "/opt/homebrew/bin/render",
        "/usr/local/bin/render",
    ):
        if cand and os.path.exists(cand):
            return cand
    sys.exit("render CLI not found. Install it or add it to PATH.")


RENDER = find_render()


def cli(*args: str, timeout: int = 300) -> str:
    proc = subprocess.run(
        [RENDER, *args], capture_output=True, text=True, timeout=timeout, cwd=HERE
    )
    return (proc.stdout or "") + (proc.stderr or "")


def check(name: str, fn):
    try:
        fn()
        print(f"  PASS  {name}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(name)
        print(f"  FAIL  {name}: {exc}")


# --------------------------------------------------------------------------
# task runs
# --------------------------------------------------------------------------

def start_task(task: str, payload: dict) -> str:
    """Start a local task run. `payload` is spread as keyword arguments.

    Note the bare object: `json.dumps` of a dict, NOT wrapped in a list. Wrapping
    it in a list is the exact mistake this file exists to prevent.
    """
    out = cli("workflows", "start", task, "--local", f"--input={json.dumps(payload)}")
    match = re.search(r"(trn-[A-Za-z0-9]+)", out)
    if not match:
        raise RuntimeError(f"could not start {task}: {out.strip()[:200]}")
    return match.group(1)


def wait_run(trn_id: str, timeout_s: int = 240, interval: int = 3) -> tuple:
    """Poll a local run until it leaves 'running'. Returns (status, text)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        out = cli("workflows", "tasks", "runs", "show", trn_id, "--local")
        status = "unknown"
        m = re.search(r"status\s+(\w+)", out)
        if m:
            status = m.group(1)
        if status in ("completed", "failed", "cancelled", "canceled"):
            return status, out
        time.sleep(interval)
    return "timeout", ""


# --------------------------------------------------------------------------
# probes
# --------------------------------------------------------------------------

def probe_tasks_registered():
    out = cli("workflows", "tasks", "list", "--local", timeout=90)
    for expected in ("ingest_document", "ingest_corpus", "retrieve", "answer"):
        assert expected in out, f"{expected} not registered"
    print("        all 4 tasks registered")


def probe_fanout():
    """The scalability claim: N documents -> N containers -> one shared dataset."""
    docs = [
        "Kestrel Analytics was founded in 2019 by Elena Sokolov and Marcus Lee.",
        "The Kestrel Pulse platform serves 340 retail locations for Bluepeak Retail.",
        "Priya Raghavan is the Support Lead and owns root cause analysis.",
    ]
    trn = start_task("ingest_corpus", {"dataset": SCRATCH, "documents": docs})
    status, out = wait_run(trn)
    assert status == "completed", f"status={status}"

    # Parse the two counters independently: the CLI prints Go's map form,
    # `map[failed:0 queued:3]`, so the order is not guaranteed and a single
    # combined regex silently never matches.
    qm = re.search(r"queued:(\d+)", out)
    fm = re.search(r"failed:(\d+)", out)
    assert qm and fm, f"no queued/failed counters in output: {out[-200:]}"
    queued, failed = int(qm.group(1)), int(fm.group(1))
    assert failed == 0, f"{failed} subtask(s) failed"
    assert queued == len(docs), f"expected {len(docs)} queued, got {queued}"
    print(f"        {queued} documents fanned out, failed:0  (scratch: {SCRATCH})")


def probe_answer_chain():
    """The chained ctx.run path. READ-ONLY against the demo dataset."""
    trn = start_task("answer", {"query": "Who owns the root cause analysis?"})
    status, out = wait_run(trn)
    assert status == "completed", f"status={status}"
    assert "Priya" in out or "Raghavan" in out, "chained answer did not return the expected name"
    print("        ctx.run chain completed and returned the right owner")


# --------------------------------------------------------------------------
# cleanup — the part that matters
# --------------------------------------------------------------------------

def delete_scratch(name: str) -> bool:
    import requests

    for d in cc.datasets():
        if d.get("name") == name:
            r = requests.delete(
                f"{cc._base()}/api/v1/datasets/{d['id']}",
                headers=cc._headers(),
                timeout=180,
            )
            return r.status_code < 300
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true",
                    help="leave the scratch dataset in place (for inspection)")
    args = ap.parse_args()

    # Refuse to run if anything about the target looks like the demo dataset.
    if SCRATCH == DEMO:
        sys.exit(f"refusing to run: scratch name collides with the demo dataset {DEMO!r}")

    print(f"Workflow smoke test — scratch dataset {SCRATCH!r}, demo dataset {DEMO!r}\n")

    try:
        check("all 4 tasks are registered", probe_tasks_registered)
        check("fan-out: N documents -> N containers, failed:0", probe_fanout)
        check("chained answer (read-only, demo dataset)", probe_answer_chain)
    finally:
        if args.keep:
            print(f"\n--keep set; left {SCRATCH!r} in place.")
        else:
            try:
                gone = delete_scratch(SCRATCH)
                print(f"\ncleanup: scratch dataset {SCRATCH!r} "
                      f"{'deleted' if gone else 'was not created'}")
            except Exception as exc:  # noqa: BLE001
                print(f"\nWARNING: could not delete {SCRATCH!r}: {exc}")
                print("         delete it by hand — do NOT leave it on the demo tenant.")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        sys.exit(1)
    print("Workflow tier is good, and the demo graph was never touched.")


if __name__ == "__main__":
    main()
