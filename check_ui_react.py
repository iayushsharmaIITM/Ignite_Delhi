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
import re
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
    # The one overlay in the app that was not a dialog at all: no role, no aria-modal,
    # no Escape, and a keyboard user could Tab straight out of it into the page behind.
    panel = page.locator('#files-sheet .sheet[role="dialog"][aria-modal="true"]')
    suite.check("the files sheet is a dialog a screen reader can announce",
                panel.count() == 1 and bool(panel.get_attribute("aria-label")),
                f"panels={panel.count()}")
    suite.check("focus moves inside when it opens", page.evaluate(
        "() => !!document.activeElement && "
        "!!document.activeElement.closest('#files-sheet .sheet')"))
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    page.keyboard.press("Tab")
    suite.check("Tab cannot walk out of the sheet into the page behind", page.evaluate(
        "() => !!document.activeElement && "
        "!!document.activeElement.closest('#files-sheet .sheet')"),
        page.evaluate("() => document.activeElement?.id || document.activeElement?.tagName"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    suite.check("Escape closes the sheet", not sheet.is_visible())
    page.click("#menu2-toggle")
    page.wait_for_timeout(250)
    page.locator("#menu2 button", has_text="Add documents").first.click()
    page.wait_for_timeout(400)
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
    # DESIGN.md promises a visible focus indicator on every control, "no exceptions".
    # What "visible" means took three attempts to get right, and each wrong version
    # produced a verdict that described the test rather than the product:
    #   * el.focus() is not a keyboard transition. Chromium decides :focus-visible from
    #     the modality of the PREVIOUS interaction, so a JS focus measured the UA
    #     default and the result depended on whether an earlier section had clicked.
    #   * the sheet animates (`transition: all`), so a sample at 0ms reads the UA
    #     default (3px #45413A) and only settles on the token after ~150ms. Every
    #     measurement below waits for it to settle.
    #   * asserting outlineStyle specifically called six controls failures when they
    #     draw their ring with box-shadow — which is how this sheet actually does it
    #     (:focus-visible { box-shadow: var(--focus) }), with an outline added only on
    #     the classes whose own reset outranked it. So: an indicator counts if EITHER
    #     channel is real, and it must be the accent token either way.
    seen, offenders = [], []
    for _ in range(14):
        page.keyboard.press("Tab")
        page.wait_for_timeout(320)
        focus = page.evaluate("""() => {
            const a = document.activeElement;
            if (!a || a === document.body) return null;
            const s = getComputedStyle(a);
            const probe = document.createElement('span');
            probe.style.color = 'var(--accent)';
            a.appendChild(probe);
            const want = getComputedStyle(probe).color;      // e.g. rgb(180, 83, 9)
            probe.remove();
            const nums = (t) => (t.match(/[0-9.]+/g) || []).map(parseFloat);
            // rgba(r,g,b,0) is a transparent shadow: present in the cascade, invisible
            // on screen. Only a non-zero alpha over the accent counts.
            const accentShadow = (s.boxShadow || 'none').split('),').some(part => {
                const n = nums(part);
                return n.length >= 4 && n[3] > 0 && Math.round(n[0]) === nums(want)[0]
                       && Math.round(n[1]) === nums(want)[1] && Math.round(n[2]) === nums(want)[2];
            }) || (s.boxShadow || '').includes(want);
            const outline = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0
                            && s.outlineColor === want;
            return {where: a.tagName + '.' + String(a.className).slice(0, 26) + (a.id ? '#' + a.id : ''),
                    fv: a.matches(':focus-visible'), outline, accentShadow,
                    os: s.outlineStyle, ow: s.outlineWidth, shadow: (s.boxShadow || '').slice(0, 34)};
        }""")
        if focus is None:
            continue
        if seen and focus["where"] == seen[0]["where"]:
            break                                   # the tab order wrapped: full cycle
        seen.append(focus)
        if not (focus["fv"] and (focus["outline"] or focus["accentShadow"])):
            offenders.append(focus)
    suite.check("the keyboard reaches a meaningful number of controls", len(seen) >= 5,
                f"{len(seen)} focused: {[f['where'] for f in seen]}")
    suite.check("every keyboard-focused control shows an accent focus indicator",
                not offenders,
                f"{len(offenders)} of {len(seen)} show nothing: {offenders[:3]}")

    suite.check("the skip link points at a real landmark",
                page.evaluate("""() => {
                    const a = document.querySelector('a[href^="#"]');
                    if (!a) return false;
                    const t = document.querySelector(a.getAttribute("href"));
                    return !!t && (t.tagName === "MAIN" || t.getAttribute("role") === "main");
                }"""))

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
    # section_settings leaves the UI in German — that is its own check — and a text
    # locator written in English then matches nothing at all. Every
    # `if locator.count():` gate below inherited that and passed by never running,
    # which is how the delete-arming check stayed invisible. Pin the locale rather
    # than trusting whatever the previous section left behind.
    page.evaluate("() => localStorage.setItem('kestrel.lang', 'en')")
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

    # Back to the brains view: opening the files sheet from a row navigates to
    # ?view=chat&brain=<name> and closing it leaves you there, so the two gates
    # below were reading a page that had neither button — which is why the
    # delete-arming check had been silently skipping for as long as it has existed.
    page.goto(base + "/?view=brains", wait_until="networkidle")
    page.wait_for_timeout(1200)

    # Create a brain. `/api/brains/v2` is flag-gated and answers 404 without
    # KESTREL_JOBS_V2, which is off everywhere except its own test — so posting
    # there unconditionally made every "Create a brain" click fail with a 404 on
    # every deployment. Nothing caught it because the local rule is single-brain
    # mode, so nobody pressed the button. The client must ask the server which
    # path exists (/api/config -> brainCreateV2) and use the one that answers.
    posts_before = len(suite.requests)
    page.route("**/api/brains", lambda route: (
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True, "name": "uitest_brain",
                                       "partial": False, "documents": 1}))
        if route.request.method == "POST" else route.continue_()))
    new_btn = page.locator("button", has_text="New brain").first
    # Not a bare `if`: a gate that skips when its trigger is missing reports
    # nothing and earns a pass. The affordance disappearing IS the regression, so
    # it is recorded as a check and only the body below is conditional.
    if suite.check("new-brain affordance exists", new_btn.count() > 0):
        new_btn.click()
        page.wait_for_timeout(400)
        suite.check("create dialog opens", page.locator("#brain-name").is_visible())
        page.fill("#brain-name", "uitest_brain")
        page.set_input_files("#brain-file-input", {"name": "a.txt",
                                                   "mimeType": "text/plain",
                                                   "buffer": b"one document"})
        page.locator("button", has_text="Create brain").first.click()
        page.wait_for_timeout(1500)
        posts = [r for r in suite.requests[posts_before:] if r.startswith("POST ")]
        suite.check("create posts the route the server answers, not the 404-by-default v2",
                    any(r.rstrip("/").endswith("/api/brains") for r in posts)
                    and not any("/api/brains/v2" in r for r in posts),
                    "posts=" + " | ".join(posts[:3]))
        suite.check("create dialog closes on success",
                    page.locator("#brain-name").count() == 0)
    page.unroute("**/api/brains")

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

    # The OAuth round-trip lands on /?connected=<provider>, and the landing pad used
    # to call setView("connectors") directly. setView moves the screen; only openView
    # moves the screen AND the address. So the user saw Connectors while the URL said
    # chat — and a reload, a bookmark, or a back press put them somewhere else entirely
    # with the success toast already gone. A failure return did the same with
    # ?connect_error. Both halves of the agreement are asserted, then proven durable by
    # a reload, because a URL that disagrees is invisible until you touch it.
    for marker in ("connected=google", "connect_error=bad_state"):
        page.goto(base + f"/?{marker}", wait_until="networkidle")
        page.wait_for_timeout(1500)
        suite.check(f"after {marker} the address names the view on screen",
                    "view=connectors" in page.url, page.url)
        suite.check(f"after {marker} the round-trip param is gone",
                    marker.split("=")[0] not in page.url, page.url)
        suite.check(f"after {marker} the connectors view is what is rendered",
                    page.locator("h1", has_text="Connectors").count() == 1,
                    f"url={page.url} h1s={page.locator('h1').all_text_contents()}")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1500)
        suite.check(f"{marker} survives a reload on the same view",
                    page.locator("h1", has_text="Connectors").count() == 1
                    and "view=connectors" in page.url,
                    page.url)

    # The owner's report, one step further along than CH-4: from ANY other
    # section, "New chat" must take you back to the composer. It did not.
    # `newChat` (App.tsx:1046) deletes ?chat and sets ?new=1 but never leaves the
    # view — no setView("chat"), no searchParams.delete("view") — so the click
    # rewrote the URL into the contradiction `?view=brains&new=1` and the screen
    # stayed on Brains. This is the same defect CH-4 fixed in `openChat`, still
    # present in its sibling, which is why the CH-4 gate above passed while the
    # button kept doing nothing. Every non-chat view is asserted, and each jump is
    # re-checked after a reload: a URL that still says view=brains reloads back to
    # Brains even if the click had appeared to work.
    for other in ("brains", "connectors", "graph"):
        page.goto(base + f"/?view={other}", wait_until="networkidle")
        page.wait_for_timeout(1200)
        newchat = page.locator("a.nav-item", has_text="New chat").first
        if newchat.count() == 0:
            suite.check(f"'New chat' is reachable from {other}", False, "no such nav item")
            continue
        newchat.click()
        page.wait_for_timeout(1200)
        suite.check(f"'New chat' from {other} drops the {other} view",
                    f"view={other}" not in page.url, page.url)
        suite.check(f"'New chat' from {other} shows the composer",
                    page.locator("textarea#q").count() == 1,
                    f"url={page.url} composers={page.locator('textarea#q').count()}")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1500)
        suite.check(f"the fresh chat started from {other} survives a reload",
                    page.locator("textarea#q").count() == 1, page.url)

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

def section_sidebar_motion(suite: Suite, base: str) -> None:
    """The sidebar retract is ONE motion, not five.

    Measured before the fix: `.shell` animated `transform .2s ease` while body
    padding-left, `.app-main` margin-left, `#f` left and `#rail` left declared no
    transition at all — so at +50ms the panel still spanned 0-114px while the content
    had already teleported to 0, and the two overlapped for ~150ms.

    Asserted by reading each element's resolved transition rather than by sampling
    wall-clock frames during the animation: a frame-sampling gate would be a coin flip
    on a slow CI runner, and the defect is a missing declaration, not a missing frame.
    Each mode is measured IN that mode, because home mode moves body padding-left while
    chat mode moves .app-main margin-left — asking a body in chat mode for a padding
    transition just returns 0, which an earlier version of this gate did and then
    reported as a failure of the stylesheet rather than of itself.
    """
    page = suite.page
    suite.section("sidebar retract motion")

    def durations() -> dict:
        return page.evaluate("""() => {
            const dur = (el, prop) => {
                if (!el) return null;
                const s = getComputedStyle(el);
                const props = s.transitionProperty.split(', ');
                const durs  = s.transitionDuration.split(', ');
                const i = props.indexOf(prop);
                return i >= 0 ? parseFloat(durs[i]) : (props.includes('all') ? parseFloat(durs[0]) : 0);
            };
            return {
                panel:    dur(document.querySelector('.shell'), 'transform'),
                bodyPad:  dur(document.body, 'padding-left'),
                main:     dur(document.querySelector('.app-main'), 'margin-left'),
                composer: dur(document.querySelector('#f'), 'left'),
                rail:     dur(document.querySelector('#rail'), 'left'),
            };
        }""")

    # --- home mode: the stack is centred by BODY padding-left -------------------
    # `?new=1`, not reset(): a plain load restores the last thread and opens in CHAT
    # mode, where `body:not(.chatting)` does not match and body padding-left is simply
    # not the moving offset. Inside the battery an earlier section always leaves a
    # thread behind, so reset() here measured 0 and the gate failed on its own
    # precondition rather than on the stylesheet.
    page.goto(base + "/?new=1", wait_until="networkidle")
    page.wait_for_timeout(1400)
    assert page.evaluate("()=>document.body.classList.contains('chatting')") is False, \
        "expected home mode to measure the body padding clock"
    home = durations()
    suite.check("home: the panel declares a transform duration to match",
                bool(home.get("panel")), str(home))
    suite.check("home: the stack moves on the panel's clock",
                home.get("bodyPad") == home.get("panel") and home["panel"] > 0, str(home))

    # --- chat mode: .app-main margin, the composer and the rail -----------------
    page.locator(".chat-item").first.click(timeout=6000)
    page.wait_for_timeout(1200)
    chat = durations()
    suite.check("chat: content, composer and rail move on the panel's clock",
                all(chat.get(k) == chat.get("panel") and chat["panel"] > 0
                    for k in ("main", "composer", "rail")), str(chat))

    # And the motion must be shared at runtime, not merely declared: sample frames and
    # require the content edge to sit ON the panel edge while it is actually moving.
    page.click(".sb-collapse")
    offsets = []
    for _ in range(4):
        page.wait_for_timeout(45)
        offsets.append(page.evaluate("""() => {
            const sb = document.querySelector('.shell').getBoundingClientRect().right;
            const m = document.querySelector('.app-main').getBoundingClientRect().left;
            return {sb: Math.round(sb), m: Math.round(m)};
        }"""))
    moving = [o for o in offsets if 0 < o["sb"] < 268]
    suite.check("mid-retract the content edge tracks the panel edge",
                bool(moving) and all(abs(o["m"] - o["sb"]) <= 2 for o in moving), str(offsets))
    page.click(".sb-toggle")
    page.wait_for_timeout(400)


def section_sidebar_hover_rail(suite: Suite, base: str) -> None:
    """The gliding rail must land on the row under the cursor — every row type.

    It did not. `.chat-item` is a DIV.nav-item wrapping an A.chat-link, and the
    selector `closest(".nav-item, .brain-row, button, a")` matched the inner LINK,
    whose offsetParent is the row rather than the nav. Position came from
    `row.offsetTop`, which is relative to whichever element happens to be the
    offsetParent — so hovering the chats list parked the rail 8px into the nav,
    284-362px above the row it was supposed to highlight. Nav items and brain rows
    were unaffected, which is why it survived review: the broken case was the one
    list in the sidebar that is always populated.

    Asserted per row type, with the chat rows required, because a gate that only
    checked nav items would have passed the whole time it was broken.
    """
    page = suite.page
    suite.section("sidebar hover rail")
    reset(suite, base)
    page.wait_for_timeout(600)
    worst = {}
    for sel, label in ((".nav-item", "nav"), (".brain-row", "brain"), (".chat-item", "chat")):
        n = page.locator(sel).count()
        if not n:
            suite.check(f"{label} rows exist to hover", False, f"0 matches for {sel}")
            continue
        errs = []
        for idx in range(min(3, n)):
            page.locator(sel).nth(idx).hover()
            page.wait_for_timeout(180)
            errs.append(page.evaluate("""(a) => {
                const rail = document.querySelector('.sb-slide');
                const row  = document.querySelectorAll(a.s)[a.i];
                const rr = rail.getBoundingClientRect(), br = row.getBoundingClientRect();
                return {top: Math.abs(Math.round(rr.top - br.top)),
                        h:   Math.abs(Math.round(rr.height - br.height)),
                        tick: rail.classList.contains('tick')};
            }""", {"s": sel, "i": idx}))
        worst[label] = max(max(e["top"] for e in errs), max(e["h"] for e in errs))
        suite.check(f"{label}: the rail lands on the hovered row ({n} present)",
                    worst[label] <= 2 and not any(e["tick"] for e in errs),
                    f"worst offset {worst[label]}px, {errs}")
    suite.check("all three row types were measured", len(worst) == 3, str(worst))


def section_stale_bundle(suite: Suite, base: str) -> None:
    """A deploy replaces the hashed bundle and deletes the previous one, so a tab
    still holding the old index.html asks for files that no longer exist. That used
    to answer as a completely BLANK page — measured live on 2026-10-04, where the
    browser requested /assets/index-SSCQYO2q.js and got a 404 with nothing on screen
    to explain it. The shell must reload once, and if that does not fix it, say so.
    """
    page = suite.page
    suite.section("stale bundle after a deploy")

    def missing(route):
        route.fulfill(status=404, body="", headers={"content-type": "text/javascript"})

    page.route("**/assets/index-*.js", missing)
    try:
        page.goto(base, wait_until="load")
        page.wait_for_timeout(6000)
        box = page.evaluate("""() => {
            const d = document.getElementById('stale-bundle');
            return d ? {role: d.getAttribute('role'),
                        text: (d.innerText || '').trim(),
                        button: !!document.getElementById('stale-reload')} : null;
        }""")
        suite.check("a missing bundle explains itself instead of rendering blank",
                    bool(box) and box.get("role") == "alert"
                    and "could not load" in (box.get("text") or "").lower()
                    and box.get("button") is True, str(box))

        # The defect this gate now guards: the retry allowance used to be a
        # once-per-session flag, so a 3-second server restart burned the single reload
        # and pinned "could not load its interface" over a healthy server until the tab
        # was closed. Age the allowance past the cooldown and the tab MUST attempt the
        # bundle again — proven by the stored timestamp being refreshed, not by waiting.
        aged = page.evaluate("""() => {
            const before = Date.now() - 30000;
            sessionStorage.setItem('kestrel.bundle.retry', String(before));
            return before;
        }""")
        page.reload(wait_until="load")
        page.wait_for_timeout(6000)
        after = page.evaluate("() => parseInt(sessionStorage.getItem('kestrel.bundle.retry') || '0', 10)")
        suite.check("an aged retry allowance attempts the bundle again instead of staying pinned",
                    after > aged, f"stored {after} vs aged {aged}")
        # And a deliberate click must not be blocked by the automatic attempt that just
        # failed: the button clears the allowance before reloading.
        cleared = page.evaluate("""() => {
            sessionStorage.setItem('kestrel.bundle.retry', String(Date.now()));
            const b = document.getElementById('stale-reload');
            if (!b) return 'no button';
            b.onclick.call(b);
            return sessionStorage.getItem('kestrel.bundle.retry');
        }""")
        suite.check("the Reload button clears the retry allowance",
                    cleared is None, f"flag after clicking Reload: {cleared}")
        page.wait_for_timeout(3000)
        page.unroute("**/assets/index-*.js", missing)

        # The false alarm this guard used to produce: a SCRIPT element also fires
        # `error` when a request is merely ABORTED, which is what Clerk's
        # `?__clerk_handshake=` redirect does on every signed-in load, and what a
        # throttled embedded browser does to a slow one. The old code reloaded on any
        # error, so a working app got pushed into the failure panel — the owner's
        # screenshot, with the bundle served 200 in the server log. An abort must not
        # spend a retry.
        def aborted(route):
            route.abort()

        page.route("**/assets/index-*.js", aborted)
        page.evaluate("() => sessionStorage.clear()")
        page.goto(base, wait_until="load")
        page.wait_for_timeout(6000)
        stamp = page.evaluate("() => sessionStorage.getItem('kestrel.bundle.retry')")
        suite.check("an aborted bundle request does not spend a reload",
                    stamp is None, f"retry stamp after an abort: {stamp}")
        page.unroute("**/assets/index-*.js", aborted)
    finally:
        suite.console.clear()


def section_graph_view(suite: Suite, base: str) -> None:
    """The graph surface, ported from static/graph.html — which this run deletes.

    The legacy page was the last hand-written UI, and it was richer than the
    in-app view that replaced it: a canvas force layout, camera zoom and pan,
    click-to-open sub-nodes over twelve core nodes, and a node inspector carrying
    properties and typed relationships. Purging it was only defensible once each
    of those four is proven here, plus the redirect that keeps old bookmarks and
    the sidebar's `/graph` href landing in the app.
    """
    page = suite.page
    suite.section("graph view")

    # The URL that used to serve a second copy of this screen must now land in
    # the app, and must keep the brain it was asked for.
    page.goto(base + "/graph?brain=company_brain", wait_until="networkidle")
    page.wait_for_timeout(1000)
    suite.check("/graph redirects into the app", "view=graph" in page.url, page.url)
    suite.check("the redirect preserves ?brain=", "brain=company_brain" in page.url, page.url)
    suite.check("/graph no longer serves a hand-written page",
                page.locator("canvas").count() >= 1, page.url)

    reset(suite, base + "/?view=graph")
    stats = (page.locator("#graph-stats").text_content() or "").strip()
    suite.check("the canvas renders", page.locator("canvas").count() == 1)
    m = re.search(r"(\d+) nodes · (\d+) edges", stats)
    suite.check("stats report real counts, not a blank canvas", bool(m) and int(m.group(1)) > 0, stats)
    node_total = int(m.group(1)) if m else 0
    # Match on the section HEADERs case-insensitively: both are rendered through
    # `text-transform: uppercase`, and inner_text() returns the transformed text,
    # so a literal "Connections (" can never match even when the panel is perfect.
    suite.check("the legend lists node types with counts",
                page.locator('[aria-label="Node types"] li').count() >= 1,
                "no legend rows")
    chips = page.locator('[aria-label^="Open "]')
    suite.check("the core nodes are reachable without a pointer",
                chips.count() >= 1, f"{chips.count()} chips")

    # Open a core node: the inspector is the whole reason clicking a node is the
    # product's answer to a 200-node graph, so it must show what the node IS.
    if chips.count():
        chips.first.click()
        page.wait_for_timeout(900)
        panel = page.locator('aside[aria-label="Node details"]')
        suite.check("opening a node shows its inspector", panel.count() == 1)
        body = (panel.first.inner_text() if panel.count() else "")
        suite.check("the inspector lists the node's connections",
                    re.search(r"connections \(\d+\)", body, re.I) is not None, body[:120])
        suite.check("opening a node counts as disclosure",
                    " opened" in (page.locator("#graph-stats").text_content() or ""),
                    (page.locator("#graph-stats").text_content() or ""))

        # A relationship row walks to the other node rather than doing nothing.
        rel = panel.locator("li button")
        if rel.count():
            rel.first.click()
            page.wait_for_timeout(900)
            suite.check("clicking a relationship walks to that node",
                        page.locator('aside[aria-label="Node details"]').count() == 1)

    zoomed = page.locator("[data-zoom]").get_attribute("data-zoom")
    page.locator('[aria-label="Zoom in"]').click()
    page.wait_for_timeout(500)
    after = page.locator("[data-zoom]").get_attribute("data-zoom")
    suite.check("zoom in changes the camera", (zoomed or "") != (after or ""), f"{zoomed} -> {after}")

    page.locator('[aria-label="Expand everything"]').click()
    page.wait_for_timeout(900)
    allstats = (page.locator("#graph-stats").text_content() or "")
    mm = re.search(r"(\d+) opened", allstats)
    suite.check("expand everything opens every node",
                bool(mm) and node_total and int(mm.group(1)) == node_total, allstats)

    page.locator('[aria-label="Collapse to core nodes"]').click()
    page.wait_for_timeout(900)
    back = (page.locator("#graph-stats").text_content() or "")
    suite.check("collapse returns to the core view", " opened" not in back, back)
    suite.check("collapse closes the inspector",
                page.locator('aside[aria-label="Node details"]').count() == 0)

    # The honesty rule: an unreachable graph must say so. It must never render as
    # an empty graph, which is the same lie A-storage-surfacing-as-empty-list is.
    page.goto(base + "/?view=graph&brain=no_such_brain_zz", wait_until="networkidle")
    page.wait_for_timeout(1200)
    err = (page.locator("#graph-stats").text_content() or "").strip()
    explained = ("Could not load" in err) or (
        page.locator("text=/graph is empty/").count() >= 1)
    suite.check("a graph it cannot fetch is explained, not shown as blank",
                explained, err[:160])


def section_graph_view(suite: Suite, base: str) -> None:
    """The graph surface, ported from static/graph.html — which this run deletes.

    The legacy page was the last hand-written UI, and it was richer than the
    in-app view that replaced it: a canvas force layout, camera zoom and pan,
    click-to-open sub-nodes over twelve core nodes, and a node inspector carrying
    properties and typed relationships. Purging it was only defensible once each
    of those four is proven here, plus the redirect that keeps old bookmarks and
    the sidebar's `/graph` href landing in the app.
    """
    page = suite.page
    suite.section("graph view")

    # The URL that used to serve a second copy of this screen must now land in
    # the app, and must keep the brain it was asked for.
    page.goto(base + "/graph?brain=company_brain", wait_until="networkidle")
    page.wait_for_timeout(1000)
    suite.check("/graph redirects into the app", "view=graph" in page.url, page.url)
    suite.check("the redirect preserves ?brain=", "brain=company_brain" in page.url, page.url)
    suite.check("/graph no longer serves a hand-written page",
                page.locator("canvas").count() >= 1, page.url)

    reset(suite, base + "/?view=graph")
    stats = (page.locator("#graph-stats").text_content() or "").strip()
    suite.check("the canvas renders", page.locator("canvas").count() == 1)
    m = re.search(r"(\d+) nodes · (\d+) edges", stats)
    suite.check("stats report real counts, not a blank canvas", bool(m) and int(m.group(1)) > 0, stats)
    node_total = int(m.group(1)) if m else 0
    # Match on the section HEADERs case-insensitively: both are rendered through
    # `text-transform: uppercase`, and inner_text() returns the transformed text,
    # so a literal "Connections (" can never match even when the panel is perfect.
    suite.check("the legend lists node types with counts",
                page.locator('[aria-label="Node types"] li').count() >= 1,
                "no legend rows")
    chips = page.locator('[aria-label^="Open "]')
    suite.check("the core nodes are reachable without a pointer",
                chips.count() >= 1, f"{chips.count()} chips")

    # Open a core node: the inspector is the whole reason clicking a node is the
    # product's answer to a 200-node graph, so it must show what the node IS.
    if chips.count():
        chips.first.click()
        page.wait_for_timeout(900)
        panel = page.locator('aside[aria-label="Node details"]')
        suite.check("opening a node shows its inspector", panel.count() == 1)
        body = (panel.first.inner_text() if panel.count() else "")
        suite.check("the inspector lists the node's connections",
                    re.search(r"connections \(\d+\)", body, re.I) is not None, body[:120])
        suite.check("opening a node counts as disclosure",
                    " opened" in (page.locator("#graph-stats").text_content() or ""),
                    (page.locator("#graph-stats").text_content() or ""))

        # A relationship row walks to the other node rather than doing nothing.
        rel = panel.locator("li button")
        if rel.count():
            rel.first.click()
            page.wait_for_timeout(900)
            suite.check("clicking a relationship walks to that node",
                        page.locator('aside[aria-label="Node details"]').count() == 1)

    zoomed = page.locator("[data-zoom]").get_attribute("data-zoom")
    page.locator('[aria-label="Zoom in"]').click()
    page.wait_for_timeout(500)
    after = page.locator("[data-zoom]").get_attribute("data-zoom")
    suite.check("zoom in changes the camera", (zoomed or "") != (after or ""), f"{zoomed} -> {after}")

    page.locator('[aria-label="Expand everything"]').click()
    page.wait_for_timeout(900)
    allstats = (page.locator("#graph-stats").text_content() or "")
    mm = re.search(r"(\d+) opened", allstats)
    suite.check("expand everything opens every node",
                bool(mm) and node_total and int(mm.group(1)) == node_total, allstats)

    page.locator('[aria-label="Collapse to core nodes"]').click()
    page.wait_for_timeout(900)
    back = (page.locator("#graph-stats").text_content() or "")
    suite.check("collapse returns to the core view", " opened" not in back, back)
    suite.check("collapse closes the inspector",
                page.locator('aside[aria-label="Node details"]').count() == 0)

    # The honesty rule: an unreachable graph must say so. It must never render as
    # an empty graph, which is the same lie A-storage-surfacing-as-empty-list is.
    page.goto(base + "/?view=graph&brain=no_such_brain_zz", wait_until="networkidle")
    page.wait_for_timeout(1200)
    err = (page.locator("#graph-stats").text_content() or "").strip()
    explained = ("Could not load" in err) or (
        page.locator("text=/graph is empty/").count() >= 1)
    suite.check("a graph it cannot fetch is explained, not shown as blank",
                explained, err[:160])


def section_phatic_in_browser(suite: Suite, base: str) -> None:
    """A greeting typed in the real UI must be answered instantly, with no citations.

    This is the end-to-end half of the phatic route. The unit tier proves the
    classifier and the table; only the browser can prove the path a user takes — that
    the client sends its locale, that the note the client appends does not blind the
    server, and that a message which is a greeting AND a question is still answered
    from the documents.
    """
    page = suite.page
    suite.section("phatic in the browser")
    reset(suite, base + "/?new=1")

    sent = len(suite.requests)
    page.fill("textarea#q", "hi")
    page.keyboard.press("Enter")
    page.wait_for_selector(".turn.bot .bubble", timeout=8000)
    first = page.evaluate("() => performance.now()")
    page.wait_for_timeout(1200)

    asks = [u for u in suite.requests[sent:] if "/api/ask" in u]
    suite.check("the client sends its locale with the question",
          any("lang=" in u for u in asks), str(asks[:1]))

    bot = page.locator(".turn.bot .bubble").last
    text = (bot.text_content() or "").strip().lower()
    log = " ".join((page.locator(".turn.bot").last.locator(".w-step").all_text_contents()))
    suite.check("a greeting is answered from the phatic route",
          "Phatic" in log, log[:160])
    suite.check("the greeting reply is the table's wording, not a fixture answer",
          "ask me anything" in text or "good morning" in text or "good afternoon" in text
          or "good evening" in text, text[:120])
    suite.check("a greeting cites nothing",
          page.locator(".turn.bot .srcs").count() == 0,
          f"{page.locator('.turn.bot .srcs').count()} citation chips on a 'hi'")
    suite.check("the reply arrived without waiting on retrieval",
          bool(re.search(r"(retrieval|graph|embed|recall)", log, re.I)) is False,
          log[:160])

    # Fail OPEN, in the browser: the greeting must not swallow the question.
    reset(suite, base + "/?new=1")
    page.fill("textarea#q", "hi, what is the Bluepeak renewal date?")
    page.keyboard.press("Enter")
    page.wait_for_selector(".turn.bot .bubble", timeout=30000)
    page.wait_for_timeout(2000)
    mixed = (page.locator(".turn.bot .bubble").last.text_content() or "").strip().lower()
    mlog = " ".join((page.locator(".turn.bot").last.locator(".w-step").all_text_contents()))
    suite.check("a greeting plus a question is NOT answered from the template",
          "ask me anything about your company" not in mixed, mixed[:120])
    suite.check("…and it went to the brain instead", "Phatic" not in mlog, mlog[:160])


SECTIONS = [
    ("chat / ask", section_chat),
    ("source modal", section_source_modal),
    ("draft box", section_draft_box),
    ("files sheet", section_files_sheet),
    ("composer menus / keyboard", section_composer_menus_keyboard),
    ("settings", section_settings),
    ("brains page", section_brains_page),
    ("graph view", section_graph_view),
    ("deep links / history", section_deep_links_history),
    ("sidebar hover rail", section_sidebar_hover_rail),
    ("sidebar retract motion", section_sidebar_motion),
    ("stale bundle", section_stale_bundle),
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

    # Preflight: this suite drives the product unauthenticated, because the browser
    # gates assert on chat and brain surfaces that a signed-out Clerk session cannot
    # reach. Since AUTH_MODE now defaults to clerk, running this against a normally
    # booted app used to produce ~25 failures that all really meant one thing. Say
    # the one thing instead.
    try:
        import urllib.request
        with urllib.request.urlopen(base.rstrip("/") + "/api/config", timeout=8) as r:
            mode = json.loads(r.read()).get("authMode")
    except Exception as exc:  # noqa: BLE001 - the suite's own gates report a dead server
        print(f"could not read {base}/api/config: {type(exc).__name__}: {str(exc)[:120]}")
        return 1
    if mode != "off":
        print(f"{base} is running AUTH_MODE={mode!r} — every request this suite makes "
              "would 401.\n"
              "Run the battery instead, which boots its own unauthenticated tier:\n"
              "    ./verify.sh\n"
              "Or point this at a tier started with:\n"
              "    PROVIDER=mock AUTH_MODE=off PORT=8028 python3 app.py")
        return 2
    print(f"React UI acceptance suite — {base} (authMode=off)\n")
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
