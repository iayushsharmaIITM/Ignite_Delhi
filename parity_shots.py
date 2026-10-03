"""Side-by-side parity captures: React (:5174) vs legacy (:8010) shell.

Usage: python3 parity_shots.py [tag]
Writes /tmp/parity/<tag>-{react,legacy}-{w}.png for w in 1440/768/390.
"""
import sys
from playwright.sync_api import sync_playwright

TAG = sys.argv[1] if len(sys.argv) > 1 else "v1"
VIEWPORTS = [(1440, 900), (768, 1024), (390, 844)]
TARGETS = [("react", "http://127.0.0.1:5174/"), ("legacy", "http://127.0.0.1:8010/")]

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    for name, url in TARGETS:
        for w, h in VIEWPORTS:
            page = browser.new_page(viewport={"width": w, "height": h})
            try:
                page.goto(url, wait_until="networkidle", timeout=20000)
            except Exception:
                pass  # networkidle can hang on long-polling; DOM is up by now
            page.wait_for_timeout(600)
            page.screenshot(path=f"/tmp/parity/{TAG}-{name}-{w}.png")
            page.close()
            print(f"{TAG}-{name}-{w}.png done")
    browser.close()
