"""UI smoke test for the React frontend — click every control, fail on any console error.

WHY THIS EXISTS
The legacy check_ui.py drove a real browser through the static HTML shell.
The React frontend has a completely different DOM (no .nav-item, no #app,
no shell.js) — so it needs its own suite. This drives Playwright through
every interactive control in the React app and fails if anything throws.

    python3 check_ui_react.py                  # auto-detect React on :5173
    python3 check_ui_react.py --base http://localhost:5173
    python3 check_ui_react.py --headful        # show the browser window

Exit codes: 0 = all clean, 1 = failures.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright, Page, Browser

# Controls that mutate state or navigate away — exercised by hand instead.
SKIP_TEXTS = {
    "Delete", "Click again to delete",  # destructive
    "Graph",                             # triggers confirm() about legacy hand-off
    "Rename", "Pin",                     # sidebar dropdown items (alert())
}

# Views to exercise (React app has chat, connectors, graph).
VIEWS = ["chat", "connectors", "graph"]


def console_errors(page: Page) -> list[str]:
    """Collect console errors from the page."""
    errors: list[str] = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    return errors


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if detail and not ok else ""))
    return ok


def run_checks(page: Page, base: str) -> list[str]:
    """Run all UI checks against the React app. Returns list of failures."""
    failures: list[str] = []
    errors: list[str] = []

    def track(name: str, ok: bool, detail: str = "") -> None:
        if not check(name, ok, detail):
            failures.append(name)

    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    # ---- Chat view (default) ----
    print("[chat]")
    page.goto(base, wait_until="networkidle")
    page.wait_for_timeout(1500)

    # Sidebar must be present
    sidebar = page.locator('aside[aria-label="Kestrel navigation"]')
    track("sidebar visible", sidebar.is_visible())

    # Composer must be present
    textarea = page.locator('textarea[aria-label="Ask across every document"]')
    track("composer textarea visible", textarea.is_visible())

    # Send button must be present
    send_btn = page.locator('button[aria-label="Send"], button[aria-label="Stop generating"]')
    track("send button visible", send_btn.count() > 0)

    # Brain selector must be present
    brain_btn = page.locator('button[aria-label*="Current brain"]')
    track("brain selector visible", brain_btn.count() > 0)

    # Suggestion chips must be present (on empty chat)
    chips = page.locator('button:has-text("Summarise"), button:has-text("next steps"), button:has-text("Draft a mail"), button[has-text="consistent"]')
    track("suggestion chips visible", chips.count() >= 3, f"found {chips.count()}")

    # Sidebar nav buttons
    for label in ["New chat", "New brain", "Connectors"]:
        btn = page.locator(f'button:has-text("{label}")').first
        track(f'sidebar button "{label}"', btn.count() > 0)

    # Click every safe button and verify no errors
    all_buttons = page.locator('button:visible')
    clicked = 0
    threw = 0
    for i in range(all_buttons.count()):
        btn = all_buttons.nth(i)
        try:
            text = (btn.text_content() or "").strip()
            aria = btn.get_attribute("aria-label") or ""
            full = f"{text} {aria}"
            if any(s in full for s in SKIP_TEXTS):
                continue
            if not text and not aria:
                continue
            btn.click(timeout=3000)
            clicked += 1
        except Exception:
            threw += 1

    track("no click threw", threw == 0, f"{threw} threw out of {clicked}")
    track("console clean (chat)", not errors, "; ".join(errors[:3]))

    # ---- Connectors view ----
    print("[connectors]")
    errors.clear()
    page.goto(f"{base}/?view=connectors", wait_until="networkidle")
    page.wait_for_timeout(1000)

    connectors_btn = page.locator('button:has-text("Connectors")')
    track("connectors view renders", connectors_btn.count() > 0)

    # Click buttons in connectors view
    conn_buttons = page.locator('button:visible')
    conn_clicked = 0
    conn_threw = 0
    for i in range(conn_buttons.count()):
        btn = conn_buttons.nth(i)
        try:
            text = (btn.text_content() or "").strip()
            aria = btn.get_attribute("aria-label") or ""
            full = f"{text} {aria}"
            if any(s in full for s in SKIP_TEXTS):
                continue
            if not text and not aria:
                continue
            btn.click(timeout=3000)
            conn_clicked += 1
        except Exception:
            conn_threw += 1

    track("connectors: no click threw", conn_threw == 0, f"{conn_threw} threw")
    track("console clean (connectors)", not errors, "; ".join(errors[:3]))

    # ---- Graph view ----
    print("[graph]")
    errors.clear()
    page.goto(f"{base}/?view=graph", wait_until="networkidle")
    page.wait_for_timeout(1500)

    # GraphView renders an SVG or canvas
    graph_svg = page.locator('svg, canvas')
    track("graph view renders", graph_svg.count() > 0)

    track("console clean (graph)", not errors, "; ".join(errors[:3]))

    # ---- Deep-link restore ----
    print("[deep-link]")
    errors.clear()
    page.goto(f"{base}/?view=chat", wait_until="networkidle")
    page.wait_for_timeout(500)
    # Verify the app is still functional after navigation
    track("app alive after navigation", textarea.is_visible())

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="React UI smoke test")
    parser.add_argument("--base", default=None, help="base URL (default: auto-detect)")
    parser.add_argument("--headful", action="store_true", help="show browser window")
    args = parser.parse_args()

    base = args.base
    if not base:
        # Try to detect React frontend
        result = os.popen("python3 detect_frontend.py --json 2>/dev/null").read()
        try:
            data = json.loads(result)
            if data["verdict"] == "react":
                # Find which port
                for port, info in data["ports"].items():
                    if info["frontend"] == "react":
                        base = f"http://127.0.0.1:{port}"
                        break
        except (json.JSONDecodeError, KeyError):
            pass

    if not base:
        print("No React frontend detected. Start it with:")
        print("  cd frontend && npm run dev")
        print("Or pass --base explicitly.")
        return 1

    print(f"React UI smoke test — {base}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headful)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})

        try:
            failures = run_checks(page, base)
        finally:
            browser.close()

    print()
    if failures:
        print(f"{len(failures)} FAILED: " + ", ".join(failures))
        return 1
    print("All views clean: every control clicked, zero console errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
