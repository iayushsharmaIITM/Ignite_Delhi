"""Export every brain's graph so the app can run with no tenant at all.

WHY THIS EXISTS
The offline fallback in fixtures/graph.json covers ONE brain — the demo. Any
other brain had no snapshot, so a deployment without the tenant could show the
demo and nothing else. This exports each brain's real graph to its own file.

The honesty rule still holds: each file is that brain's OWN data. A snapshot is
never served for a brain it does not describe, because a fabricated graph looks
exactly like a real one.

    python snapshot.py                 # every brain on the tenant
    python snapshot.py --dataset x     # just one

Output:
    fixtures/brains/<name>.json        {nodes, edges} — lean, view-only
    fixtures/brains/index.json         manifest: names, counts, export time
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "fixtures" / "brains"

import cognee_cloud as cc  # noqa: E402


def lean(graph: dict) -> dict:
    """Keep only what the view draws.

    Node `properties` are dropped: they include whole source passages, which
    would take the payload from ~70KB to ~190KB per brain for data the graph
    canvas never renders. The inspector reads properties from the LIVE graph.
    """
    return {
        "nodes": [
            {"id": n.get("id"), "label": n.get("label", ""), "type": n.get("type", "")}
            for n in graph.get("nodes", [])
        ],
        "edges": [
            {"source": e.get("source"), "target": e.get("target"), "label": e.get("label")}
            for e in graph.get("edges", [])
        ],
    }


def _safe_name(raw: str) -> str:
    """H8: --dataset is an unsanitized filesystem path (`--dataset ../../evil`
    writes outside fixtures/brains/). Normalize exactly like the app edge —
    and refuse when nothing usable is left rather than writing a wrong file."""
    import re as _re
    name = (raw or "").strip().lower()
    name = _re.sub(r"[\s\-.]+", "_", name)
    name = _re.sub(r"[^a-z0-9_]", "", name)
    name = _re.sub(r"_{2,}", "_", name).strip("_")
    if not _re.fullmatch(r"[a-z0-9][a-z0-9_]{2,39}", name):
        sys.exit(f"Refusing to export: {raw!r} is not a valid brain name.")
    return name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=None,
                    help="export only this brain (default: every brain)")
    args = ap.parse_args()

    if not cc.configured():
        sys.exit("COGNEE_SERVICE_URL and COGNEE_API_KEY must both be set (see .env).")

    if args.dataset:
        names = [_safe_name(args.dataset)]
    else:
        try:
            names = sorted(_safe_name(d.get("name") or "")
                           for d in cc.datasets() if d.get("name"))
        except Exception as exc:  # noqa: BLE001
            sys.exit(f"Could not list datasets: {exc}")

    if not names:
        sys.exit("No datasets found on the tenant.")

    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "brains": {},
    }

    for name in names:
        try:
            graph = cc.graph(name)
        except Exception as exc:  # noqa: BLE001
            print(f"  {name:<20} SKIPPED: {str(exc)[:80]}")
            continue

        data = lean(graph)
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

        manifest["brains"][name] = {
            "nodes": len(data["nodes"]),
            "edges": len(data["edges"]),
            "bytes": path.stat().st_size,
        }
        print(f"  {name:<20} {len(data['nodes']):>4} nodes  "
              f"{len(data['edges']):>4} edges  {path.stat().st_size // 1024} KB")

    # LOW-8: write the manifest atomically. The old code wrote index.json
    # unconditionally at the end — an all-failed run overwrote a good
    # manifest with an empty one. Tmp + replace only when something exported.
    if manifest["brains"]:
        tmp = OUT / "index.json.tmp"
        tmp.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        tmp.replace(OUT / "index.json")
    else:
        print("Nothing exported — leaving the existing manifest untouched.")
    total = sum(b["bytes"] for b in manifest["brains"].values())
    print(f"\n{len(manifest['brains'])} brain(s) exported, {total // 1024} KB total")
    print(f"Manifest: fixtures/brains/index.json")
    return 0 if manifest["brains"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
