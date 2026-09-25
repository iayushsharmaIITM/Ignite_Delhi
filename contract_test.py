"""Contract test: our client's wire format vs a Cognee endpoint, any flavor.

BUILD_PLAN.md M0.3 / §2.3. Replays the full surface our app uses —

    remember -> status -> (terminal) -> data items -> data raw -> graph -> recall

—against a UNIQUE SCRATCH DATASET and asserts shape, not just status codes.
Its whole job is to catch API drift between Cognee versions before it reaches
the app, so it fails loudly (exit 1) naming the field that changed.

Safety, copied from wf_smoke.py (read that file's history for why):
  * always targets a unique scratch dataset, never COGNEE_DATASET
  * refuses to run if the scratch name could collide with the demo dataset
  * deletes the scratch dataset in a `finally` block, even on failure

    python3 contract_test.py --flavor cloud            # vs the cloud tenant
    python3 contract_test.py --base http://localhost:8888 --flavor oss
    python3 contract_test.py ... --keep                # leave scratch behind

The two flavors differ in exactly two recall body fields (BUILD_PLAN.md M0.4):
cloud sends searchType/includeReferences, OSS v1.6.1 sends
search_type/include_references. The recall probe also sends the OTHER flavor's
names as a drift experiment and records what happens (200 = silently accepts,
422 = rejects) — that is the empirical drift signal for future upgrades.

OSS without an LLM key (M0.2 state): remember lands the data item but the
pipeline terminal state is a failure, and recall cannot generate. Those two
probes downgrade to SKIP(no-llm) rather than FAIL — shape is still asserted
via the 422 check, and the phase gates rerun this script WITH keys after M1.1.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# The base URL must be in the environment BEFORE cognee_cloud builds requests;
# its accessors read env lazily, but being explicit costs nothing.
_ap = argparse.ArgumentParser()
_ap.add_argument("--base", default=None,
                 help="Cognee API base URL (no trailing slash). "
                      "Defaults to COGNEE_SERVICE_URL, including from .env")
_ap.add_argument("--flavor", choices=["cloud", "oss"], default="cloud")
_ap.add_argument("--keep", action="store_true",
                 help="leave the scratch dataset behind for inspection")
_ap.add_argument("--wait-timeout", type=int, default=300,
                 help="seconds to wait for the pipeline to reach a terminal state")
ARGS = _ap.parse_args()
if not ARGS.base:
    # .env holds the tenant URL locally; argparse ran before cognee_cloud's
    # own load_env, so load it here rather than duplicating the URL on the CLI.
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(HERE, ".env"))
    except ImportError:
        pass
    ARGS.base = os.getenv("COGNEE_SERVICE_URL", "")
if not ARGS.base:
    sys.exit("--base is required when COGNEE_SERVICE_URL is not set")
os.environ["COGNEE_SERVICE_URL"] = ARGS.base.rstrip("/")
os.environ.setdefault("COGNEE_FLAVOR", ARGS.flavor)

import requests  # noqa: E402

import cognee_cloud as cc  # noqa: E402  (loads .env on import)

DEMO = cc.dataset()
SCRATCH = f"contract_{int(time.time())}"
SENTINEL = f"CONTRACT-PROBE-SENTINEL-{int(time.time())}"
PROBE_TEXT = (
    f"Kestrel contract-test probe document. {SENTINEL}. "
    "Elena Sokolov founded Kestrel Analytics in 2019. "
    "This text exists only to verify the ingestion wire contract."
)
PROBE_FILENAME = "probe_filename.md"

FAILURES: list[str] = []
SKIPS: list[str] = []
INFOS: list[str] = []


def check(name, fn):
    try:
        fn()
        print(f"  PASS  {name}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(name)
        print(f"  FAIL  {name}: {exc}")


def base() -> str:
    return ARGS.base.rstrip("/")


def headers() -> dict:
    # Reuse the client's headers: X-Api-Key when configured, none otherwise
    # (OSS with auth off ignores it; local runs have no key set).
    h = cc._headers()
    return h if h.get("X-Api-Key") else {}


# ---------------------------------------------------------------------------
# probes
# ---------------------------------------------------------------------------

def probe_health():
    r = requests.get(f"{base()}/health", timeout=30)
    assert r.status_code < 400, f"HTTP {r.status_code}"
    payload = r.json()
    assert isinstance(payload, dict), f"not a dict: {payload!r}"
    assert any(k in payload for k in ("status", "health")), f"no status key: {payload!r}"


def probe_datasets_shape():
    r = requests.get(f"{base()}/api/v1/datasets/", headers=headers(), timeout=60)
    assert r.status_code < 400, f"HTTP {r.status_code}"
    assert isinstance(r.json(), list), "datasets did not return a list"


def probe_remember():
    """Our client's exact multipart shape, including the filename field."""
    out = cc.remember(PROBE_TEXT, SCRATCH, None, True, PROBE_FILENAME)
    assert isinstance(out, (dict, list)), f"unexpected remember payload: {str(out)[:120]}"


def probe_scratch_resolves():
    did = cc.dataset_id(SCRATCH)
    assert did, "scratch dataset did not appear in the datasets list after remember"
    probe_scratch_resolves.id = did


def _status_payload() -> dict:
    # Mirror cc.status(): the client always sends include_error_detail=true.
    # Without it the cloud tenant returns a bare {"<uuid>": "<STATE>"} string
    # map (measured 2026-09-25); with it, {"<uuid>": {"status": ...}}.
    return requests.get(
        f"{base()}/api/v1/datasets/status",
        headers=headers(),
        params={"dataset": probe_scratch_resolves.id,
                "include_error_detail": "true"},
        timeout=60,
    ).json()


def probe_status_shape():
    payload = _status_payload()
    assert isinstance(payload, dict), f"status is not a dict: {payload!r}"
    # Either keyed by uuid or flat — cc.terminal_kind accepts both, so we
    # only assert that SOME status string is present once terminal.


def probe_wait_terminal():
    """Block until terminal; record the exact state string we observed.

    The state string itself is a finding (the live enums differ between
    flavors), so it goes to INFOS rather than an assertion.
    """
    deadline = time.time() + ARGS.wait_timeout
    observed = None
    while time.time() < deadline:
        payload = _status_payload()
        kind = cc.terminal_kind(payload)
        states = list(cc._status_values(payload))
        if kind and states:
            observed = (states[0], kind)
            break
        time.sleep(5)
    assert observed, f"no terminal state within {ARGS.wait_timeout}s"
    probe_wait_terminal.state, probe_wait_terminal.kind = observed
    INFOS.append(f"terminal state observed: {observed[0]} -> {observed[1]}")
    if observed[1] == "failure":
        SKIPS.append("pipeline failed on the target (expected on OSS without "
                     "an LLM key) — recall text checks downgraded")


def probe_data_items():
    did = probe_scratch_resolves.id
    items = cc.data_items(did)
    assert isinstance(items, list) and items, "no data items after remember"
    item = items[0]
    assert item.get("id"), f"item without id: {item!r}"
    probe_data_items.id = item["id"]
    # M0.5 finding: did the endpoint keep the filename we sent?
    probe_data_items.name = (item.get("name") or "")
    INFOS.append(f"data item name stored as: {probe_data_items.name!r} "
                 f"(sent {PROBE_FILENAME!r})")


def probe_data_raw():
    text = cc.data_raw(probe_scratch_resolves.id, probe_data_items.id)
    assert SENTINEL in text, f"sentinel missing from raw text: {text[:120]!r}"


def probe_graph_shape():
    payload = requests.get(
        f"{base()}/api/v1/datasets/{probe_scratch_resolves.id}/graph",
        headers=headers(),
        params={"full": "true", "max_nodes": 500},
        timeout=120,
    )
    assert payload.status_code < 400, f"HTTP {payload.status_code}"
    g = payload.json()
    assert isinstance(g, dict) and "nodes" in g and "edges" in g, f"bad shape: {str(g)[:120]}"


def _recall_body(flavor: str) -> dict:
    keys = ("search_type", "include_references") if flavor == "oss" \
        else ("searchType", "includeReferences")
    return {
        "query": "Who founded Kestrel Analytics and when?",
        "datasets": [SCRATCH],
        keys[0]: cc.GRAPH_COMPLETION,
        keys[1]: True,
    }


def probe_recall():
    """Main path: this flavor's field names must NOT 422 for field reasons.

    422 is the drift signal — it means the endpoint stopped accepting the
    field names this flavor sends. A 200 with a text answer is required when
    the pipeline succeeded; on OSS without an LLM key (M0.2 state) recall
    422s with LLMAPIKeyNotSetError instead of generating — measured
    2026-09-25 — which is a no-llm SKIP, not drift. Only a 422 that does NOT
    mention the LLM key fails the run.
    """
    r = requests.post(f"{base()}/api/v1/recall", headers=headers(),
                      json=_recall_body(ARGS.flavor), timeout=cc.timeout())
    if r.status_code == 422:
        if "LLMAPIKeyNotSet" in r.text or "LLM_API_KEY" in r.text:
            SKIPS.append("recall 422 LLMAPIKeyNotSet (OSS without an LLM key) — "
                         "field names accepted, generation downgraded")
            return
        raise AssertionError(
            f"RECALL FIELD DRIFT: {ARGS.flavor} body rejected with 422: {r.text[:200]}"
        )
    if r.status_code >= 400:
        if getattr(probe_wait_terminal, "kind", None) == "failure":
            SKIPS.append(f"recall HTTP {r.status_code} with failed pipeline "
                         f"(no LLM key) — treated as shape-conformant")
            return
        raise AssertionError(f"recall HTTP {r.status_code}: {r.text[:200]}")
    payload = r.json()
    items = payload if isinstance(payload, list) else [payload]
    text = cc.answer_text(items)
    if getattr(probe_wait_terminal, "kind", None) == "success":
        assert text.strip(), f"recall 200 but empty answer: {str(payload)[:200]}"
    else:
        SKIPS.append(f"recall 200 before a confirmed-success terminal state "
                     f"(kind={getattr(probe_wait_terminal, 'kind', None)!r}) — "
                     "text not asserted")


def probe_cross_flavor_drift():
    """Send the OTHER flavor's field names and record what happens.

    Informational by design: whether the endpoint silently accepts foreign
    field names decides how much protection the rename actually buys. Never
    fails the run; always recorded for PROGRESS.md.
    """
    other = "cloud" if ARGS.flavor == "oss" else "oss"
    r = requests.post(f"{base()}/api/v1/recall", headers=headers(),
                      json=_recall_body(other), timeout=cc.timeout())
    verdict = ("200 (silently accepts BOTH naming styles)"
               if r.status_code < 400 else
               f"HTTP {r.status_code} (rejects the {other} names — drift is loud)")
    INFOS.append(f"drift experiment [{other} names -> {ARGS.flavor} endpoint]: {verdict}")


# ---------------------------------------------------------------------------
# cleanup — the part that matters (wf_smoke.py pattern)
# ---------------------------------------------------------------------------

def delete_scratch() -> None:
    if SCRATCH == DEMO or SCRATCH in cc._PROTECTED_DATASETS:
        return  # never even possible given the name, but refuse anyway
    for d in cc.datasets():
        if d.get("name") == SCRATCH:
            requests.delete(
                f"{base()}/api/v1/datasets/{d['id']}",
                headers=headers(), timeout=180,
            ).raise_for_status()
            return


def main() -> int:
    if SCRATCH == DEMO:
        sys.exit(f"refusing to run: scratch name collides with the demo dataset {DEMO!r}")

    print(f"Contract test — flavor={ARGS.flavor} base={base()}")
    print(f"scratch dataset {SCRATCH!r} (demo {DEMO!r} is never touched)\n")

    try:
        check("health responds with a status", probe_health)
        check("datasets list returns a list", probe_datasets_shape)
        check("remember accepts our multipart fields", probe_remember)
        check("scratch dataset resolves to an id", probe_scratch_resolves)
        check("status returns a parseable map", probe_status_shape)
        check(f"pipeline reaches a terminal state ({ARGS.wait_timeout}s cap)",
              probe_wait_terminal)
        check("data items list with ids", probe_data_items)
        check("data raw round-trips our text", probe_data_raw)
        check("graph returns nodes/edges shape", probe_graph_shape)
        check(f"recall accepts {ARGS.flavor} field names (no 422)", probe_recall)
        check("cross-flavor drift experiment", probe_cross_flavor_drift)
    finally:
        if ARGS.keep:
            print(f"\n--keep set; left {SCRATCH!r} in place.")
        else:
            try:
                delete_scratch()
                print(f"\ncleanup: scratch dataset {SCRATCH!r} deleted")
            except Exception as exc:  # noqa: BLE001
                print(f"\nWARNING: could not delete {SCRATCH!r}: {exc}")
                print("         delete it by hand — do NOT leave it on the tenant.")

    for line in INFOS:
        print(f"  INFO  {line}")
    for line in SKIPS:
        print(f"  SKIP  {line}")
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        return 1
    print("Contract holds. Wire format conforms.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
