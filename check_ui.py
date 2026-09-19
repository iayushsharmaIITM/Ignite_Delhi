"""UI smoke test — click everything on every page, fail on any console error.

WHY THIS EXISTS
A deleted function left a dangling variable reference. Nothing caught it: the
JS parsed, every suite passed, and the page rendered. The feature only broke
when a user CLICKED the button. Static checks cannot see that.

So this drives a real browser through every page, clicks every control, and
fails if anything throws. It is the test that would have caught the SOURCES
bug, and the next one like it.

    python check_ui.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NODE_BIN = "/Users/_iayushsharma_/.workbuddy-ai/binaries/node/workspace/node_modules/.bin"
BASE = "http://127.0.0.1:8000"

PAGES = ["/", "/graph", "/brains", "/upload"]

# Buttons that would mutate state or navigate away. Clicking them is either
# destructive or leaves the page, so they are exercised by hand instead.
SKIP_CLICK = ("Delete", "Clear", "Export", "Plain text", "New brain", "switch brain", "Choose files", "Browse", "Select")

FAILED: list[str] = []


def pcli(*args: str, timeout: int = 90) -> str:
    env = dict(os.environ)
    env["PATH"] = NODE_BIN + os.pathsep + env.get("PATH", "")
    proc = subprocess.run(
        ["playwright-cli", *args], capture_output=True, text=True,
        timeout=timeout, env=env, cwd=HERE,
    )
    return proc.stdout + proc.stderr


def console_errors() -> list[str]:
    """Real console errors only.

    The summary line reads "Total messages: 0 (Errors: 0, Warnings: 0)", so
    grepping for the word "Error" flagged a perfectly clean console. Parse the
    count, then collect the actual message lines.
    """
    out = pcli("console")
    m = re.search(r"Errors:\s*(\d+)", out)
    if m and int(m.group(1)) == 0:
        return []
    bad = [
        ln.strip() for ln in out.splitlines()
        if re.search(r"\b(ReferenceError|TypeError|SyntaxError|Uncaught)\b", ln)
        and "Errors:" not in ln
    ]
    if m and int(m.group(1)) > 0 and not bad:
        bad = [f"{m.group(1)} console error(s) reported"]
    return bad


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        FAILED.append(name)


def main() -> int:
    print("UI smoke test — clicking every control on every page\n")
    pcli("close-all")

    if pcli("open", "--browser=webkit", BASE).strip() == "":
        print("  (browser open produced no output)")

    for page in PAGES:
        print(f"[{page}]")
        pcli("goto", BASE + page)
        pcli("resize", "1440", "1000")
        # Let the page settle: graph layout, health fetch, brains list.
        pcli("eval", "() => new Promise(r => setTimeout(r, 2500))")

        # How many clickable controls are there, and do any throw?
        script = """() => {
          // The drop zone and the file input open a native file dialog, which
          // blocks the page and breaks every subsequent check.
          const els = [...document.querySelectorAll('button, .chip, .act, a[href^="#"]')]
            .filter(el => !el.closest('#drop, .drop, form[enctype]')
                          && el.id !== 'pick' && el.tagName !== 'INPUT');
          const skip = %s;
          const clicked = [];
          let threw = 0;
          for (const el of els) {
            const label = (el.textContent || '').trim().slice(0, 24);
            if (!label || skip.some(s => label.startsWith(s))) continue;
            try { el.click(); clicked.push(label); }
            catch (e) { threw++; }
          }
          return { total: els.length, clicked: clicked.length, threw };
        }""" % json.dumps(list(SKIP_CLICK))

        out = pcli("eval", script)
        m = re.search(r"\{[\s\S]*?\}", out)
        stats = json.loads(m.group(0)) if m else {"total": 0, "clicked": 0, "threw": 0}

        check(f"{page} rendered controls", stats["total"] > 0, f"found {stats['total']}")
        check(f"{page} no click threw", stats["threw"] == 0, f"{stats['threw']} threw")

        # The real signal: did anything log an error while we clicked?
        errors = console_errors()
        check(f"{page} console clean", not errors, "; ".join(errors[:3]))

        # The sidebar must be present on every page — it is injected by shell.js,
        # so a silent failure there would leave every page without navigation.
        nav = pcli("eval", "() => document.querySelectorAll('.nav-item').length")
        nav_n = int(re.search(r"\d+", nav).group(0)) if re.search(r"\d+", nav) else 0
        check(f"{page} sidebar injected", nav_n >= 4, f"{nav_n} nav items")

    pcli("close-all")
    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED: " + ", ".join(FAILED))
        return 1
    print("All pages clean: every control clicked, zero console errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
