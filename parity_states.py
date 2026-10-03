"""Interactive-state parity captures: thread, menus, collapsed sidebar.

Usage: python3 parity_states.py [tag]
For each target (react :5174 / legacy :8010):
  - ask a question, wait for the (honest) failure turn -> thread state
  - open the ⋯ menu  -> menu2 state
  - open the brain switcher -> brainmenu state
  - retract the sidebar -> collapsed state
"""
import sys
from playwright.sync_api import sync_playwright

TAG = sys.argv[1] if len(sys.argv) > 1 else "s1"
TARGETS = [("react", "http://127.0.0.1:5174/"), ("legacy", "http://127.0.0.1:8010/")]
Q = "Why is the Bluepeak renewal at risk?"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    for name, url in TARGETS:
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            page.goto(url, wait_until="networkidle", timeout=20000)
        except Exception:
            pass
        page.wait_for_timeout(500)
        # ask -> thread + working log + (honest) error answer
        page.fill("#q", Q)
        page.press("#q", "Enter")
        page.wait_for_timeout(9000)
        page.screenshot(path=f"/tmp/parity/{TAG}-{name}-thread.png")
        # composer menus
        page.click("#menu2-toggle")
        page.wait_for_timeout(350)
        page.screenshot(path=f"/tmp/parity/{TAG}-{name}-menu2.png")
        page.keyboard.press("Escape")
        page.click("#brainswitch")
        page.wait_for_timeout(600)
        page.screenshot(path=f"/tmp/parity/{TAG}-{name}-brainmenu.png")
        page.keyboard.press("Escape")
        # retract sidebar
        page.click(".sb-collapse")
        page.wait_for_timeout(400)
        page.screenshot(path=f"/tmp/parity/{TAG}-{name}-collapsed.png")
        page.close()
        print(f"{name} states done")
    browser.close()
