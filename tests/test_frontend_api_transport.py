"""Static gate: every frontend API call goes through the one transport.

    python3 tests/test_frontend_api_transport.py

Why: the port's headline defect was that /api/ask, /api/chats, /api/brains and
friends were called with a bare fetch() and no Authorization header, so on the
live stack (AUTH_MODE=clerk) they all 401'd and rendered as empty data. The fix
is a single `apiFetch` in lib/api.ts that awaits Clerk boot and mints a token
per request. Nothing stops a future component from reaching for fetch() again —
except this check. It also asserts that the served artifact exists and that
index.html's own asset references resolve, since app.py serves frontend/dist.

Two exemptions exist, and both must say so in the code:
  * lib/api.ts owns the transport; lib/clerk.ts loads the Clerk script itself.
  * Top-level OAuth navigations (`window.location.href = "/api/connectors/..."`)
    must NOT go through apiFetch — they are browser navigations that hand off to
    the provider and return through the server. A line is only exempt if the
    three lines above it contain `transport-exempt`.

No browser, no network: a source/artifact check that runs in the fast lane.
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "frontend", "src")

# lib/api.ts owns the transport; lib/clerk.ts loads the Clerk script itself.
ALLOWED_FILES = {"lib/api.ts", "lib/clerk.ts"}
EXEMPT_MARKER = "transport-exempt"

FETCH_CALL = re.compile(r"(?<![\w.])fetch\s*\(")
API_LITERAL = re.compile(r"[\"'`]/api/")
COMMENT = re.compile(r"^\s*(//|\*|/\*)")


def source_files() -> list[tuple[str, str, list[str]]]:
    out = []
    for dirpath, _dirnames, filenames in os.walk(SRC):
        for name in sorted(filenames):
            if not name.endswith((".ts", ".tsx")):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, SRC).replace(os.sep, "/")
            with open(path, encoding="utf-8") as fh:
                out.append((rel, path, fh.read().splitlines()))
    return out


def main() -> int:
    failures: list[str] = []
    files = source_files()

    for rel, _path, lines in files:
        if rel in ALLOWED_FILES:
            continue
        for i, line in enumerate(lines):
            if COMMENT.match(line):
                continue
            window = lines[max(0, i - 3): i + 1]
            exempt = any(EXEMPT_MARKER in w for w in window)

            if FETCH_CALL.search(line) and not exempt:
                failures.append(
                    f"{rel}:{i + 1} calls fetch() directly — use apiFetch from "
                    f"@/lib/api (docs/FRONTEND_FIX_PLAN.md B1)"
                )
                continue

            if API_LITERAL.search(line) and not exempt:
                # an apiFetch( call may wrap onto the previous/next line — fine
                prev = lines[i - 1] if i else ""
                nxt = lines[i + 1] if i + 1 < len(lines) else ""
                if "apiFetch(" in (prev + line + nxt):
                    continue
                failures.append(
                    f"{rel}:{i + 1} reaches an /api/... URL outside apiFetch "
                    f"(add a `{EXEMPT_MARKER}` comment if it is an OAuth navigation)"
                )

    # The served artifact (app.py mounts frontend/dist when KESTREL_UI=react).
    dist = os.path.join(ROOT, "frontend", "dist")
    index = os.path.join(dist, "index.html")
    if not os.path.isfile(index):
        failures.append("frontend/dist/index.html is missing — run ops/build_frontend.sh")
    else:
        with open(index, encoding="utf-8") as fh:
            html = fh.read()
        for asset in sorted(set(re.findall(r"/assets/[A-Za-z0-9._-]+", html))):
            if not os.path.isfile(os.path.join(dist, asset.lstrip("/"))):
                failures.append(f"frontend/dist{asset} is referenced by index.html but missing")

    print(f"transport check: {len(files)} source files scanned")
    if failures:
        print(f"\n{len(failures)} FAILED:")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS — every /api call goes through apiFetch, and the served bundle is complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
