"""React UI acceptance suite — the served bundle, driven like a user.

    python3 check_ui_react.py                       # auto-detect the running app
    python3 check_ui_react.py --base http://127.0.0.1:8020
    python3 check_ui_react.py --headful             # watch it

What this replaces
------------------
The old suite predated the port: it described a React DOM with "no .nav-item,
no shell.js", clicked every button on three views and called that coverage. It
could not see a broken ask, a lost citation, a draft that never opened, a chat
that would not restore, or Back/Forward going nowhere.

This one drives the real surfaces with the model-dependent calls intercepted
(canned NDJSON — no provider, no cost, deterministic) and asserts OUTCOMES:

  * ask → both turns appear immediately, steps stream into the turn's own log,
    the answer renders, citations arrive after `done`, the log collapses and
    re-expands, and the conversation is saved and remembered in the URL
  * citation chip → source modal with the verbatim passage highlighted
  * ⋯ menu → add-documents sheet, per-file verdicts and the pipeline stream
  * draft box → generated draft, and Send quoting the server's refusal
  * brains page → rows, live stats, two-step armed delete
  * composer menus, keyboard (Enter / Shift+Enter / Escape)
  * deep links + Back/Forward (the URL and the screen agree)
  * a restored chat keeps its per-turn logs, attachments and citations

Exit 0 = every claim above held, and the console stayed clean throughout.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from playwright.sync_api import Page, sync_playwright

VIEW_SIZES = {"desktop": (1440, 1000), "mobile": (390, 844)}

SOURCE_DOC = "05_policy_SLA-credit-01.md"

# Canned /api/ask stream: the shape the server actually emits (orchestrator
# {stage:"step"} rows, {type:"chunk"}, and {type:"references"} AFTER
# {stage:"done"} — the ordering that used to lose the chips on reload).
ANSWER = (
    "The **Bluepeak renewal** is at risk because the service credit was approved "
    "outside the SLA window.\n\n"
    "- Owner: Tomás Ferrer\n"
    "- Credit: 12%\n"
)
ASK_STREAM = "".join(
    json.dumps(ev) + "\n"
    for ev in [
        {"stage": "start", "dataset": "company_brain"},
        {"stage": "step", "label": "Router: general chat — bypassing retrieval agents", "ms": 120},
        {"stage": "step", "label": "Delegating to graph_agent", "ms": 900},
        {"type": "chunk", "text": ANSWER[:60]},
        {"type": "chunk", "text": ANSWER[60:160]},
        {"type": "chunk", "text": ANSWER[160:]},
        {"stage": "done"},
        {"type": "references", "items": [
            # A phrase that actually occurs in the document: the modal
            # highlights by searching the excerpt, so a made-up one renders no
            # <mark> at all.
            {"source": SOURCE_DOC,
             "excerpt": "To ensure service credits are granted consistently"},
        ]},
    ]
)

RESTORED_TURNS = [
    {"role": "user", "text": "What did we promise Bluepeak?", "at": 1759400000000,
     "attachments": [{"name": "sla.pdf", "kind": "file", "size": 1234}]},
    {"role": "bot", "text": "We promised a 12% service credit.", "at": 1759400004000,
     "workedMs": 2400,
     "steps": [{"label": "Router: general chat — bypassing retrieval agents", "at": 1759400000500, "ms": 120},
               {"label": "Delegating to graph_agent", "at": 1759400001000, "ms": 900}],
     "sources": [{"source": SOURCE_DOC,
                  "excerpt": "To ensure service credits are granted consistently"}]},
]


def reset(suite: Suite, url: str) -> None:
    """Every section starts from a known page: a section that aborts inside an
    overlay used to leave the next one clicking at a covered screen."""
    suite.page.goto(url, wait_until="networkidle")
    suite.page.wait_for_timeout(1100)



def launch(p, headless: bool = True):
    """Chrome when asked for (or when it is what is installed), chromium in CI.

    Local dev has Chrome and no Playwright-managed chromium; the CI job installs
    chromium and has no Chrome channel. KESTREL_TEST_BROWSER picks.
    """
    want = os.environ.get("KESTREL_TEST_BROWSER", "chrome").lower()
    if want == "chromium":
        return p.chromium.launch(headless=headless)
    try:
        return p.chromium.launch(channel="chrome", headless=headless)
    except Exception:  # noqa: BLE001 - fall back to whatever is installed
        return p.chromium.launch(headless=headless)


class Suite:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.failures: list[str] = []
        self.console: list[str] = []
        self.requests: list[str] = []
        page.on("console", lambda m: self.console.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: self.console.append(str(e)))
        page.on("request", lambda r: self.requests.append(f"{r.method} {r.url}"))

    # ---- reporting -------------------------------------------------------
    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not ok else ""))
        if not ok:
            self.failures.append(name)
        return ok

    def section(self, title: str) -> None:
        print(f"[{title}]")

    def console_clean(self, label: str) -> None:
        real = [c for c in self.console if "Failed to load resource" not in c]
        self.check(f"console clean ({label})", not real, "; ".join(real[:3]))
        self.console.clear()

    def asked(self, needle: str) -> bool:
        return any(needle in r for r in self.requests)

    # ---- routing ---------------------------------------------------------
    def intercept(self) -> None:
        page = self.page
        page.route("**/api/ask*", lambda route: route.fulfill(
            status=200, content_type="application/x-ndjson", body=ASK_STREAM))
        page.route("**/api/chats", lambda route: (
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True}))
            if route.request.method == "POST" else route.continue_()
        ))
        page.route("**/api/chats/smoke-restore", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "chat": {"id": "smoke-restore", "turns": RESTORED_TURNS}})))
        page.route("**/api/actions/draft", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "draft": {
                "to": "tomas@bluepeak.example",
                "subject": "Bluepeak renewal",
                "body": "Hi Tomás,\n\nStatus per the SLA."}})))
        page.route("**/api/actions/send", lambda route: route.fulfill(
            status=503, content_type="application/json",
            body=json.dumps({"detail": "Email sending is not configured."})))
        page.route("**/api/brains", lambda route: (
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True, "documents": 1, "appended": True,
                                           "ingested": [{"name": "notes.txt", "ok": True}]}))
            if route.request.method == "POST" else route.continue_()
        ))
        page.route("**/api/brains/*/events*", lambda route: route.fulfill(
            status=200, content_type="application/x-ndjson",
            body=json.dumps({"stage": "poll", "state": "INGESTING"}) + "\n"
                 + json.dumps({"stage": "ready"}) + "\n"))


def section_chat(suite: Suite, base: str) -> None:
    page = suite.page
    reset(suite, base)
    page = suite.page
    suite.section("chat / ask")
    suite.check("react shell served", page.locator("#root").count() == 1)
    suite.check("composer present", page.locator("textarea#q").is_visible())
    suite.check("sidebar present", page.locator('aside[aria-label="Kestrel navigation"]').is_visible())
    suite.check("sliding rail mounted", page.locator(".sb-slide").count() == 1)

    page.locator(".chip").first.click()
    page.wait_for_timeout(250)
    suite.check("starter chip fills the composer", bool(page.input_value("#q").strip()))
    page.fill("#q", "")

    page.fill("#q", "Why is the Bluepeak renewal at risk?")
    page.press("#q", "Enter")
    page.wait_for_timeout(1500)

    suite.check("user turn appears", page.locator(".turn.user").count() >= 1)
    suite.check("bot turn appears immediately", page.locator(".turn.bot").count() >= 1)
    suite.check("answer rendered",
                "Bluepeak renewal" in (page.locator(".turn.bot .bubble").last.text_content() or ""))
    steps = page.locator(".turn.bot .w-step")
    suite.check("working log has the engine's steps", steps.count() >= 2, f"{steps.count()} steps")
    suite.check("step durations measured", "·" in (steps.first.text_content() or ""))
    suite.check("citation chips rendered", page.locator(".turn .srcs button").count() >= 1)
    acts = page.locator(".turn.bot .msg-acts button")
    suite.check("message actions present", acts.count() >= 3, f"{acts.count()} actions")
    suite.check("working log collapsed after done", page.locator(".working.collapsed").count() >= 1)
    page.locator(".working-head").first.click()
    page.wait_for_timeout(250)
    suite.check("working log re-expands on click",
                "collapsed" not in (page.locator(".working").first.get_attribute("class") or "collapsed"))
    page.locator(".working-head").first.click()
    page.wait_for_timeout(200)

    suite.check("conversation saved", any(
        r.startswith("POST") and "/api/chats" in r for r in suite.requests))
    suite.check("URL remembers the chat", "chat=" in page.url)
    suite.check("?new=1 cleared from the URL", "new=1" not in page.url)
    suite.console_clean("ask")

def section_source_modal(suite: Suite, base: str) -> None:
    page = suite.page
    reset(suite, base)
    page = suite.page
    # ---------------------------------------------------------------- source modal
    suite.section("source modal")
    page.locator(".turn .srcs button").first.click()
    page.wait_for_timeout(900)
    modal = page.locator("#source-modal")
    suite.check("modal opens", modal.is_visible())
    suite.check("modal names the document", SOURCE_DOC in (page.locator("#src-name").text_content() or ""))
    suite.check("origin line shown", "corpus" in (page.locator("#src-where").text_content() or "").lower())
    suite.check("cited passage highlighted", page.locator("#source-modal mark").count() >= 1)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    suite.check("Escape closes the modal", not modal.is_visible())
    page.locator(".turn .srcs button").first.click()
    page.wait_for_timeout(800)
    page.mouse.click(20, 20)
    page.wait_for_timeout(300)
    suite.check("backdrop click closes the modal", not modal.is_visible())
    suite.console_clean("source modal")

def section_draft_box(suite: Suite, base: str) -> None:
    page = suite.page
    reset(suite, base)
    page = suite.page
    # ---------------------------------------------------------------- draft
    suite.section("draft box")
    page.locator('.turn.bot .msg-acts button[title*="mail" i]').last.click()
    page.wait_for_timeout(900)
    draft = page.locator("#draft textarea")
    suite.check("draft box opens", draft.count() >= 1)
    suite.check("draft body prefilled",
                "Status per the SLA" in (draft.input_value() if draft.count() else ""))
    page.locator("#draft button", has_text="Send").first.click()
    page.wait_for_timeout(1000)
    toasts = page.locator("[data-sonner-toast]")
    toast_text = " ".join(toasts.all_text_contents()) if toasts.count() else ""
    suite.check("send failure quotes the server", "not configured" in toast_text,
                toast_text[:120] or "no toast")
    page.locator("#draft button", has_text="Close").first.click()
    page.wait_for_timeout(300)
    suite.console_clean("draft")

def section_files_sheet(suite: Suite, base: str) -> None:
    page = suite.page
    # The demo brain is deliberately read-only; uploads need a brain that accepts documents.
    reset(suite, base + "/?brain=kestrel_full")
    page = suite.page
    # ---------------------------------------------------------------- files sheet
    suite.section("files sheet")
    page.click("#menu2-toggle")
    page.wait_for_timeout(250)
    page.locator("#menu2 button", has_text="Add documents").first.click()
    page.wait_for_timeout(400)
    sheet = page.locator("#files-sheet")
    suite.check("sheet opens from the ⋯ menu", sheet.is_visible())
    suite.check("drop zone present", page.locator("#files-sheet .drop").count() == 1)
    page.set_input_files("#file-input", {"name": "notes.txt", "mimeType": "text/plain",
                                         "buffer": b"Bluepeak notes"})
    page.wait_for_timeout(300)
    suite.check("picked file listed", page.locator("#filelist li").count() >= 1)
    page.click("#files-go")
    page.wait_for_timeout(1600)
    suite.check("per-file verdict from the server",
                "added" in (page.locator("#filelist").text_content() or ""))
    suite.check("pipeline reported",
                "complete" in (page.locator("#pipeline").text_content() or "").lower())
    page.click("#files-close")
    page.wait_for_timeout(300)
    suite.console_clean("files sheet")

def section_composer_menus_keyboard(suite: Suite, base: str) -> None:
    page = suite.page
    reset(suite, base)
    page = suite.page
    # ---------------------------------------------------------------- menus + keyboard
    suite.section("composer menus / keyboard")
    page.click("#brainswitch")
    page.wait_for_timeout(300)
    suite.check("brain menu opens", page.locator("#brainmenu").is_visible())
    suite.check("brain menu lists options", page.locator("#brainmenu button").count() >= 1)
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    suite.check("Escape closes the brain menu", not page.locator("#brainmenu").is_visible())

    page.click("#menu2-toggle")
    page.wait_for_timeout(250)
    menu2 = page.locator("#menu2")
    suite.check("⋯ menu opens", menu2.is_visible())
    suite.check("question count shown", "question" in (menu2.text_content() or "").lower())
    suite.check("export items present", page.locator("#export-md").count() == 1)
    page.locator("#clear-chat").click()
    page.wait_for_timeout(250)
    suite.check("clear arms before acting",
                "Really clear" in (page.locator("#clear-chat").text_content() or ""))
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    page.fill("#q", "first line")
    page.press("#q", "Shift+Enter")
    page.wait_for_timeout(200)
    suite.check("Shift+Enter inserts a newline", "\n" in page.input_value("#q"))
    turns_before = page.locator(".turn").count()
    page.press("#q", "Enter")
    page.wait_for_timeout(1200)
    suite.check("Enter sends", page.locator(".turn").count() > turns_before)
    suite.console_clean("menus")

def target_brain_name(text: str) -> str:
    """The brain a files-sheet is pointed at, read off its label.

    FilesSheet renders `into <brain>` (FilesSheet.tsx:151), or "into the demo
    brain (read-only)" when no brain is selected. The `into ` prefix is label
    text, not part of the name — comparing the whole label against a row could
    never match, because no row contains the word "into".
    """
    t = (text or "").strip()
    if t.startswith("into "):
        t = t[len("into "):].strip()
    return "" if not t or t.startswith("the demo brain") else t


def section_settings(suite: Suite, base: str) -> None:
    """The settings surface, in the auth mode this suite runs in.

    Legacy rendered the gear only in clerk mode, so an auth-off deployment (the
    self-host/local case) had no path to language, theme, usage, upgrade or
    connectors at all. The item set must match the legacy pop:
    language, theme | usage, upgrade, connectors (| account, sign-out when
    signed in — absent here, and asserted absent).
    """
    page = suite.page
    suite.section("settings")
    suite.check("settings row present", page.locator("#sb-user").is_visible())
    gear = page.locator("#sb-user .gear")
    suite.check("gear present", gear.is_visible())

    gear.click()
    page.wait_for_timeout(400)
    pop = page.locator(".settings-pop")
    suite.check("menu opens", pop.is_visible())
    items = [x.strip() for x in pop.locator("button").all_text_contents() if x.strip()]
    for label in ["Language", "App theme", "Usage stats", "Upgrade", "Connectors"]:
        suite.check(f"menu has {label}", any(label in i for i in items), str(items))
    suite.check("account items hidden when signed out",
                not any("account" in i.lower() or "disconnect" in i.lower() for i in items), str(items))
    box = pop.bounding_box()
    suite.check("menu is anchored, not at the viewport origin",
                bool(box) and box["x"] >= 0 and box["y"] > 0, str(box))

    # language submenu → live switch (no reload)
    pop.locator(".set-item", has_text="Language").click()
    page.wait_for_timeout(400)
    sub = page.locator(".sub-pop")
    suite.check("language submenu opens", sub.is_visible())
    sub.locator("button", has_text="Deutsch").click()
    page.wait_for_timeout(600)
    nav = " ".join(page.locator(".nav-item span").all_text_contents()[:3])
    suite.check("language switches live", "Neuer Chat" in nav, nav)
    suite.check("<html lang> follows", page.evaluate("() => document.documentElement.lang") == "de")

    # back to English (later sections assert English copy)
    gear.click()
    page.wait_for_timeout(300)
    pop.locator(".set-item", has_text="Sprache").click()
    page.wait_for_timeout(400)
    page.locator(".sub-pop button", has_text="English").click()
    page.wait_for_timeout(500)

    # theme submenu
    gear.click()
    page.wait_for_timeout(300)
    pop.locator(".set-item", has_text="App theme").click()
    page.wait_for_timeout(400)
    page.locator(".sub-pop button", has_text="Dark theme").click()
    page.wait_for_timeout(600)
    suite.check("theme switches live", page.evaluate("() => document.documentElement.dataset.theme") == "dark")
    gear.click()
    page.wait_for_timeout(300)
    pop.locator(".set-item", has_text="App theme").click()
    page.wait_for_timeout(400)
    page.locator(".sub-pop button", has_text="System default").click()
    page.wait_for_timeout(400)

    # usage
    gear.click()
    page.wait_for_timeout(300)
    pop.locator(".set-item", has_text="Usage stats").click()
    page.wait_for_timeout(1500)
    sheet = page.locator(".km-sheet")
    suite.check("usage modal opens", sheet.is_visible())
    suite.check("usage modal has a real state",
                "Usage stats" in (sheet.text_content() or "")
                and ("Feature" in (sheet.text_content() or "") or "No model calls" in (sheet.text_content() or "")),
                (sheet.text_content() or "")[:80])
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    suite.check("Escape closes the modal", not sheet.is_visible())

    # upgrade
    gear.click()
    page.wait_for_timeout(300)
    pop.locator(".set-item", has_text="Upgrade").click()
    page.wait_for_timeout(600)
    suite.check("upgrade modal opens", page.locator(".km-sheet").is_visible())
    suite.check("upgrade lists the three tiers", page.locator(".tier").count() == 3)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # connectors is reachable from here in every mode
    gear.click()
    page.wait_for_timeout(300)
    pop.locator(".set-item", has_text="Connectors").click()
    page.wait_for_timeout(1200)
    suite.check("connectors view opens from the menu",
                page.locator("h1", has_text="Connectors").count() == 1)
    suite.console_clean("settings")


def section_brains_page(suite: Suite, base: str) -> None:
    page = suite.page
    reset(suite, base + "/?view=brains")
    page = suite.page
    # ---------------------------------------------------------------- brains page
    suite.section("brains page")
    page.goto(base + "/?view=brains", wait_until="networkidle")
    page.wait_for_timeout(1500)
    suite.check("brains page renders", page.locator("h1", has_text="Brains").count() == 1)
    rows = page.locator('ul[aria-label="Brain list"] li')
    suite.check("brain rows listed", rows.count() >= 1, f"{rows.count()} rows")
    if rows.count():
        suite.check("live graph stats shown", "nodes" in (rows.first.text_content() or ""))
    # The brains page's own actions are in-app after the legacy /upload page was
    # retired (it now redirects here): "Add documents" must open the files sheet
    # for that brain, not navigate away.
    add_btn = page.locator('ul[aria-label="Brain list"] li button', has_text="Add documents").first
    if add_btn.count():
        # Capture the row this button belongs to BEFORE opening the sheet, so the
        # assertion is "this row's brain", not "some brain in the list".
        row_text = add_btn.locator("xpath=ancestor::li[1]").text_content() or ""
        add_btn.click()
        page.wait_for_timeout(900)
        sheet = page.locator("#files-sheet")
        suite.check("brains row 'Add documents' opens the sheet in-app", sheet.is_visible())
        target = page.locator("#files-target").text_content() or ""
        name = target_brain_name(target)
        suite.check("sheet targets the row's brain",
                    bool(name) and name in row_text,
                    "target=" + target[:40] + " row=" + row_text[:40])
        suite.check("no navigation away from the app", "/upload" not in page.url)
        page.click("#files-close")
        page.wait_for_timeout(300)

    del_btn = page.locator("button", has_text="Delete").first
    if del_btn.count():
        del_btn.click()
        page.wait_for_timeout(250)
        suite.check("delete arms first", "Confirm" in (del_btn.text_content() or ""))
    suite.console_clean("brains")

def section_deep_links_history(suite: Suite, base: str) -> None:
    page = suite.page
    reset(suite, base)
    page = suite.page
    # ---------------------------------------------------------------- deep links + history
    suite.section("deep links / history")
    page.goto(base + "/?view=graph", wait_until="networkidle")
    page.wait_for_timeout(1000)
    suite.check("graph view renders", page.locator("svg").count() >= 1)
    page.go_back()
    page.wait_for_timeout(1200)
    suite.check("Back returns to the chat view", page.locator("textarea#q").is_visible())
    page.go_forward()
    page.wait_for_timeout(1000)
    suite.check("Forward returns to the graph view", "graph" in page.url)
    page.goto(base + "/?chat=smoke-restore", wait_until="networkidle")
    page.wait_for_timeout(1500)
    suite.check("restored chat renders its turns", page.locator(".turn").count() >= 2)
    suite.check("restored turn keeps its working log", page.locator(".turn.bot .w-step").count() >= 1)
    suite.check("restored attachment rendered", page.locator(".turn.user .atts .att").count() >= 1)
    suite.check("restored bot turn has its citation", page.locator(".turn .srcs button").count() >= 1)

    # CH-4 / the owner's report: opening a chat from ANOTHER view must land on
    # the chat and stay there. `openChat` used to write ?chat= without clearing
    # ?view=, so the conversation loaded while the screen stayed on Brains, and
    # a reload proved it. Two checks, both new: the click zone (the row's left
    # strip used to be padding outside the link) and the URL agreeing with the
    # view after the jump and after a reload.
    page.goto(base + "/?view=brains", wait_until="networkidle")
    page.wait_for_timeout(1200)
    row = page.locator(".nav-item.chat-item").first
    if row.count():
        box = row.bounding_box()
        page.mouse.click(box["x"] + 8, box["y"] + box["height"] / 2)
        page.wait_for_timeout(1500)
        suite.check("clicking a chat row's LEFT strip opens it", "chat=" in page.url, page.url)
        suite.check("the stale view param is cleared", "view=" not in page.url, page.url)
        suite.check("the conversation is on screen", page.locator(".turn").count() >= 2,
                    f"{page.locator('.turn').count()} turns")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1500)
        suite.check("the jump survives a reload", page.locator(".turn").count() >= 2,
                    page.url)
    else:
        suite.check("chat rows exist to click", False, "none in the sidebar")

    # CH-14: switching brain mid-stream must ABANDON the old conversation, not
    # carry it into the new brain (it used to stay visible, and the next save
    # filed brain A's history under brain B). Needs two brains; skipped if this
    # fixture set only has one.
    page.goto(base + "/?new=1", wait_until="networkidle")
    page.wait_for_timeout(1200)
    page.fill("textarea#q", "Walk me through the Bluepeak renewal")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1200)
    partial = (page.locator(".bubble").last.text_content() or "").strip()
    page.locator('[aria-label="Switch brain"]').click()
    page.wait_for_timeout(400)
    menu = page.locator("#brainmenu")
    opts = menu.locator("button")
    if menu.is_visible() and opts.count() >= 2:
        current = (page.locator("#brainname").text_content() or "").strip()
        idx = next((i for i in range(opts.count())
                    if not (opts.nth(i).text_content() or "").strip().startswith(current)), None)
        if idx is not None:
            opts.nth(idx).click()          # arms (a live chat needs a confirm)
            page.wait_for_timeout(300)
            opts.nth(idx).click()          # confirms
            page.wait_for_timeout(2500)
            suite.check("switching brain mid-stream clears the thread",
                        page.locator(".bubble").count() == 0,
                        f"{page.locator('.bubble').count()} bubbles left")
            body = page.locator("#thread-wrap").text_content() or ""
            suite.check("the abandoned answer did not follow into the new brain",
                        bool(partial) and partial[:40] not in body,
                        f"leaked {partial[:40]!r}")
        else:
            suite.check("a second brain was offered to switch to", False, str(idx))
    else:
        print("  note  only one brain in this fixture set — CH-14 switch not exercised")
    suite.console_clean("deep links")

SECTIONS = [
    ("chat / ask", section_chat),
    ("source modal", section_source_modal),
    ("draft box", section_draft_box),
    ("files sheet", section_files_sheet),
    ("composer menus / keyboard", section_composer_menus_keyboard),
    ("settings", section_settings),
    ("brains page", section_brains_page),
    ("deep links / history", section_deep_links_history),
]


def run(suite: Suite, base: str) -> None:
    for name, fn in SECTIONS:
        try:
            fn(suite, base)
        except Exception as exc:  # noqa: BLE001 - one broken section must not
            # hide the others: report it and keep going.
            suite.check(f"{name}: section completed", False, str(exc).splitlines()[0][:180])
            suite.console.clear()


def main() -> int:
    parser = argparse.ArgumentParser(description="React UI acceptance suite")
    parser.add_argument("--base", default=None, help="base URL (default: auto-detect)")
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()

    base = args.base
    if not base:
        result = os.popen("python3 detect_frontend.py --json 2>/dev/null").read()
        try:
            data = json.loads(result)
            for port, info in data.get("ports", {}).items():
                if info.get("frontend") == "react":
                    base = f"http://127.0.0.1:{port}"
                    break
        except (json.JSONDecodeError, KeyError):
            pass
    if not base:
        print("No React frontend detected. Start it with `python3 app.py` "
              "(KESTREL_UI=react) or `cd frontend && npm run dev`, or pass --base.")
        return 1

    print(f"React UI acceptance suite — {base}\n")
    with sync_playwright() as p:
        browser = launch(p, headless=not args.headful)
        page = browser.new_page(viewport={"width": VIEW_SIZES["desktop"][0],
                                          "height": VIEW_SIZES["desktop"][1]})
        suite = Suite(page)
        suite.intercept()
        try:
            run(suite, base)
        finally:
            browser.close()

    print()
    if suite.failures:
        print(f"{len(suite.failures)} FAILED: " + ", ".join(suite.failures))
        return 1
    print("All sections clean: ask, citations, draft, files, menus, keyboard, "
          "deep links and history — zero console errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
