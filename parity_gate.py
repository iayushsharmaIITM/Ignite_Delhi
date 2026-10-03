"""Pixel regression gate for the served React app.

    python3 parity_gate.py                     # compare against the baseline
    python3 parity_gate.py --update            # (re)write the baseline
    python3 parity_gate.py --base http://127.0.0.1:8020 --threshold 1.0

Why a baseline and not a diff against the legacy shell
------------------------------------------------------
parity_shots.py / parity_states.py capture React and the legacy twin side by
side for a human to compare — that is how the port was verified. They cannot be
a gate: Phase C deliberately changed the rendering (self-hosted Inter instead of
the system stack, `text-accent` from a 5%-white wash to the brand amber), so a
React-vs-legacy diff would now fail by design.

This gate answers the question that must stay answerable after any change: did
we move anything we did not mean to move? It captures the served app in a fixed
set of states and diffs against committed reference images using a strong-pixel
threshold (a channel delta above 24/255 counts as changed).

Baselines are per-platform (font rasterisation differs between macOS and Linux),
so the folder is tagged: baselines/<tag>/<state>-<width>.png. If no baseline
exists for the running platform the gate SKIPS with a message rather than
inventing a verdict, and --update creates it.

Exit 0 = every state within threshold. Exit 1 = drift, with the state names.
"""
from __future__ import annotations

import argparse
import os
import sys

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE_ROOT = os.path.join(HERE, "docs", "ui-review", "baselines")
WIDTHS = [1440, 768, 390]
THEMES = ["dark", "light"]
STRONG = 24  # a per-channel delta above this counts as a changed pixel


def platform_tag() -> str:
    return "darwin" if sys.platform == "darwin" else ("linux" if sys.platform.startswith("linux") else sys.platform)


def capture(base: str, out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    written = []
    with sync_playwright() as p:
        want = os.environ.get("KESTREL_TEST_BROWSER", "chrome").lower()
        if want == "chromium":
            browser = p.chromium.launch(headless=True)
        else:
            try:
                browser = p.chromium.launch(channel="chrome", headless=True)
            except Exception:  # noqa: BLE001 - fall back to whatever is installed
                browser = p.chromium.launch(headless=True)
        for theme in THEMES:
            for width in WIDTHS:
                page = browser.new_page(viewport={"width": width, "height": 900})
                # The theme is a localStorage setting the app reads at boot.
                page.add_init_script(
                    f"() => localStorage.setItem('kestrel.theme', {theme!r})")
                # Deterministic content: no greeting-by-clock, no chat history.
                page.goto(base + "/?new=1", wait_until="networkidle")
                page.wait_for_timeout(1400)
                page.evaluate(
                    "() => { const g = document.getElementById('greeting'); if (g) g.textContent = 'GREETING'; }")
                path = os.path.join(out_dir, f"home-{theme}-{width}.png")
                page.screenshot(path=path)
                page.close()
                written.append(path)
        browser.close()
    return written


def diff_ratio(a_path: str, b_path: str) -> float:
    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB")
    if a.size != b.size:
        return 1.0
    diff = ImageChops.difference(a, b).convert("L")
    changed = diff.point(lambda v: 255 if v > STRONG else 0)
    histogram = changed.histogram()
    return histogram[255] / float(a.size[0] * a.size[1])


def main() -> int:
    parser = argparse.ArgumentParser(description="Pixel regression gate (React frontend)")
    parser.add_argument("--base", default=os.environ.get("KESTREL_BASE", "http://127.0.0.1:8000"))
    parser.add_argument("--update", action="store_true", help="write the baseline instead of comparing")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="percent of pixels allowed to differ strongly (default 0.5)")
    parser.add_argument("--tag", default=None, help="platform tag (default: the current platform)")
    args = parser.parse_args()

    tag = args.tag or platform_tag()
    base_dir = os.path.join(BASELINE_ROOT, tag)
    current_dir = os.path.join(HERE, "var", "parity", tag)

    if args.update:
        files = capture(args.base, base_dir)
        print(f"baseline written: {len(files)} states → {os.path.relpath(base_dir, HERE)}")
        return 0

    if not os.path.isdir(base_dir) or not os.listdir(base_dir):
        print(f"SKIP — no baseline for platform '{tag}' "
              f"({os.path.relpath(base_dir, HERE)}). Create one with `--update` on a "
              f"machine of this platform; the behavioural suite is the real gate "
              f"elsewhere (check_ui_react.py).")
        return 0

    capture(args.base, current_dir)
    failures = []
    print(f"pixel gate — base {args.base}, threshold {args.threshold}% strong pixels")
    for theme in THEMES:
        for width in WIDTHS:
            name = f"home-{theme}-{width}.png"
            ref = os.path.join(base_dir, name)
            cur = os.path.join(current_dir, name)
            if not os.path.isfile(ref):
                print(f"  SKIP  {name} (not in the baseline; run --update)")
                continue
            ratio = diff_ratio(ref, cur) * 100.0
            ok = ratio <= args.threshold
            print(f"  {'PASS' if ok else 'FAIL'}  {name}  {ratio:.3f}% changed")
            if not ok:
                failures.append(f"{name} ({ratio:.3f}% > {args.threshold}%)")

    if failures:
        print(f"\n{len(failures)} state(s) drifted: " + ", ".join(failures))
        print(f"current captures: {os.path.relpath(current_dir, HERE)}")
        print("If the change was intended, refresh the baseline with `--update` "
              "and say so in the commit message.")
        return 1
    print("\nPASS — no unintended rendering drift.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
