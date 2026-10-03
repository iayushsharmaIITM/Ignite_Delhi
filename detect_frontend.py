"""Detect which Kestrel frontend is live — React (Vite) or legacy (static HTML).

Probes ports 5173 (Vite dev server) and 8000 (FastAPI static), then inspects
served HTML for unambiguous markers. Returns a machine-readable verdict.

    python3 detect_frontend.py           # auto-detect
    python3 detect_frontend.py --json    # JSON output for scripts
    python3 detect_frontend.py --port 5173  # probe a specific port

Exit codes: 0 = detected, 1 = nothing found / ambiguous.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error

TIMEOUT = 3

# HTML markers that unambiguously identify each frontend.
REACT_MARKERS = ('id="root"', "vite", "/src/main.tsx")
LEGACY_MARKERS = ("ui.js", "auth.js", "shell.css")

# A SERVED React build (python app.py, KESTREL_UI=react) looks different from the
# Vite dev server: no /@vite/client, no main.tsx — a hashed bundle under /assets.
# Missing this was why the detector reported "legacy" while React was live.
SERVED_REACT_MARKERS = ('id="root"', "/assets/index-")

# The dev server ports we actually see. 5174 is the documented local port
# (ops/docs use it); 5173 is Vite's default.
DEFAULT_PORTS = [5174, 5173, 8000]


def probe_port(port: int) -> dict:
    """Fetch a port and return {reachable, headers, html_snippet}."""
    url = f"http://127.0.0.1:{port}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "kestrel-detect/1"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read(16384).decode("utf-8", errors="replace")
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return {"reachable": True, "headers": headers, "html": body}
    except (urllib.error.URLError, OSError):
        return {"reachable": False, "headers": {}, "html": ""}


def classify(port: int, data: dict) -> str | None:
    """Return 'react', 'legacy', or None for a single port's response."""
    if not data["reachable"]:
        return None
    html_lower = data["html"].lower()
    headers = data["headers"]

    # React / Vite signals
    has_root = 'id="root"' in html_lower
    has_vite_header = "x-vite-dev-server" in headers or "vite" in headers.get("server", "")
    has_main_tsx = "main.tsx" in html_lower

    # Legacy signals (script tags in <head> — reliably within first 8KB)
    has_ui_js = "ui.js" in html_lower
    has_auth_js = "auth.js" in html_lower
    has_shell_css = "shell.css" in html_lower

    if has_root and (has_vite_header or has_main_tsx):
        return "react"
    # a built bundle served by the backend at "/"
    if has_root and all(m in html_lower for m in SERVED_REACT_MARKERS) \
            and not (has_ui_js or has_auth_js):
        return "react"
    if (has_ui_js or has_auth_js) and has_shell_css:
        return "legacy"
    # Fallback: if only one marker set is present
    if has_root and not (has_ui_js or has_auth_js):
        return "react"
    if (has_ui_js or has_auth_js) and not has_root:
        return "legacy"
    return None


def detect(preferred_port: int | None = None) -> dict:
    """Probe both ports and return a verdict dict."""
    ports_to_probe = [preferred_port] if preferred_port else DEFAULT_PORTS
    results: dict[int, dict] = {}
    verdicts: dict[int, str | None] = {}

    for port in ports_to_probe:
        if port is None:
            continue
        data = probe_port(port)
        results[port] = data
        verdicts[port] = classify(port, data)

    # Decide overall verdict
    detected = [(p, v) for p, v in verdicts.items() if v]
    if not detected:
        overall = "none"
    elif len(detected) == 1:
        overall = detected[0][1]
    else:
        # Both detected — prefer the one on the preferred port, or React if 5173
        if preferred_port and verdicts.get(preferred_port):
            overall = verdicts[preferred_port]
        elif 5173 in verdicts and verdicts[5173]:
            overall = verdicts[5173]
        else:
            overall = detected[0][1]

    return {
        "verdict": overall,
        "ports": {
            str(p): {
                "reachable": results[p]["reachable"],
                "frontend": verdicts[p],
            }
            for p in results
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect which Kestrel frontend is live")
    parser.add_argument("--json", action="store_true", help="output JSON")
    parser.add_argument("--port", type=int, default=None, help="probe a specific port only")
    parser.add_argument("--ports", default=None,
                        help="comma-separated ports to probe (default: 5174,5173,8000)")
    args = parser.parse_args()

    if args.ports:
        global DEFAULT_PORTS
        DEFAULT_PORTS = [int(p) for p in args.ports.split(",") if p.strip()]
    result = detect(preferred_port=args.port)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        v = result["verdict"]
        if v == "none":
            print("No Kestrel frontend detected on :5173 or :8000")
        else:
            port_info = ", ".join(
                f"{p}={info['frontend'] or 'unknown'}"
                for p, info in result["ports"].items()
            )
            print(f"Detected: {v}  ({port_info})")

    return 0 if result["verdict"] != "none" else 1


if __name__ == "__main__":
    sys.exit(main())
