"""Regression tests for pipeline terminal-state handling.

Run:  python test_pipeline_states.py

WHY THIS FILE EXISTS
--------------------
The upload path used to report a FAILED ingestion as a finished, working brain.
`is_terminal()` treated success and failure states identically, the event stream
emitted `ready` for any terminal state, and the UI printed "Pipeline complete"
with a link to a dashboard that could not answer anything.

Two separate defects, both covered here:
  1. `terminal_kind()` must classify success and failure apart.
  2. The event stream must never emit `ready` for a failure.

It also pins the subtler bug: `is_terminal()` used to lowercase the WHOLE JSON
payload and substring-search it. Because `status()` asks for
`include_error_detail=true`, error text mentioning "failed" made a still-running
dataset look terminal — and it was then reported as ready.
"""

from __future__ import annotations

import asyncio
import json
import sys

import app as app_module
import cognee_cloud

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name}  {detail}")


def state(status: str, **extra) -> dict:
    return {"ab526f7c-cafc-5b95-a44a-54973f88aa2f": {"status": status, **extra}}


# ---------------------------------------------------------------------------
# 1. terminal_kind — classification
# ---------------------------------------------------------------------------

def test_classification() -> None:
    print("\n[classification]")

    check(
        "running is not terminal",
        cognee_cloud.terminal_kind(state("DATASET_PROCESSING_STARTED")) is None,
    )
    check(
        "completed -> success",
        cognee_cloud.terminal_kind(state("DATASET_PROCESSING_COMPLETED")) == "success",
    )
    check(
        "failed -> failure",
        cognee_cloud.terminal_kind(state("DATASET_PROCESSING_FAILED")) == "failure",
    )
    check(
        "errored -> failure",
        cognee_cloud.terminal_kind(state("DATASET_PROCESSING_ERRORED")) == "failure",
    )
    check(
        "flat payload shape is accepted",
        cognee_cloud.terminal_kind({"status": "DATASET_PROCESSING_COMPLETED"}) == "success",
    )

    # THE TRAP. These two were reported as ready by the old implementation.
    check(
        "TRAP: running + error_detail mentioning 'failed' stays running",
        cognee_cloud.terminal_kind(
            state("DATASET_PROCESSING_STARTED", error_detail="previous run failed")
        )
        is None,
        "the old whole-blob substring match reported this as terminal",
    )
    check(
        "TRAP: running + reason mentioning 'completed' stays running",
        cognee_cloud.terminal_kind(
            state("DATASET_PROCESSING_STARTED", reason="not completed yet")
        )
        is None,
    )

    check(
        "is_terminal still works as a wrapper",
        cognee_cloud.is_terminal(state("DATASET_PROCESSING_COMPLETED")) is True
        and cognee_cloud.is_terminal(state("DATASET_PROCESSING_STARTED")) is False,
    )


# ---------------------------------------------------------------------------
# 2. the event stream — the user-visible contract
# ---------------------------------------------------------------------------

async def drive(states: list) -> list:
    """Run brain_events against a stubbed status() and collect the events."""
    calls = {"n": 0}

    def fake_status(_name=None, **_kw):
        index = min(calls["n"], len(states) - 1)
        calls["n"] += 1
        return states[index]

    original = cognee_cloud.status
    cognee_cloud.status = fake_status
    try:
        response = await app_module.brain_events("probe")
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
    finally:
        cognee_cloud.status = original

    return [json.loads(line) for line in "".join(chunks).splitlines() if line.strip()]


def test_event_stream() -> None:
    print("\n[event stream]")

    events = asyncio.run(drive([state("DATASET_PROCESSING_FAILED")]))
    stages = [e.get("stage") for e in events]
    check(
        "failure emits stage=failed",
        "failed" in stages,
        f"stages were {stages}",
    )
    check(
        "failure NEVER emits stage=ready",
        "ready" not in stages,
        f"stages were {stages}",
    )
    detail = next((e.get("detail") for e in events if e.get("stage") == "failed"), "")
    check("failure carries a reason for the user", bool(detail), f"detail={detail!r}")

    events = asyncio.run(drive([state("DATASET_PROCESSING_COMPLETED")]))
    stages = [e.get("stage") for e in events]
    check("success emits stage=ready", "ready" in stages, f"stages were {stages}")
    check("success does not emit stage=failed", "failed" not in stages, f"stages were {stages}")


def main() -> int:
    test_classification()
    test_event_stream()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("failed: " + ", ".join(FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
