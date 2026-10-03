"""Static gate: no Tailwind colour utility is used without a definition.

    python3 tests/test_frontend_css_utilities.py

Why: `index.css`'s @theme block mapped only a subset of the Deck tokens into
Tailwind roles, so ~120 utilities (bg-panel, border-line-2, text-fg-2, bg-wash,
text-accent, …) were used across the components while emitting NO CSS AT ALL.
Nothing failed: the build was green, the pages rendered, and the surfaces just
quietly lost their backgrounds and borders. `text-accent` was the worst of them
— mapped to `var(--wash)`, i.e. 5%-white text.

The check is deliberately narrow: every `bg-*/text-*/border-*/ring-*/fill-*/
stroke-*/divide-*/placeholder-*` token that appears in frontend/src must have a
rule in the built stylesheet (or in one of the legacy stylesheets, which define
the custom classes the port re-uses). Anything else is a class that does nothing.

Run after `ops/build_frontend.sh`; it reads frontend/dist CSS, so it also fails
loudly if the bundle was never built.
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "frontend", "src")
DIST = os.path.join(ROOT, "frontend", "dist")

PREFIXES = (
    "bg-", "text-", "border-", "ring-", "fill-", "stroke-",
    "divide-", "placeholder-", "from-", "via-", "to-",
)

# Tokens that look like utilities but are not: prose that happens to start with
# a prefix, and the two deliberate no-op classes. Each needs a reason.
ALLOWED: dict[str, str] = {}

TOKEN = re.compile(r"[A-Za-z0-9:_\[\]\/.,%#()!$&*+=>~^-]+")
ESCAPE = re.compile(r"([^A-Za-z0-9_-])")


def escaped_selector(cls: str) -> str:
    return "." + ESCAPE.sub(r"\\\1", cls)


def collect_css() -> str:
    chunks = []
    assets = os.path.join(DIST, "assets")
    if os.path.isdir(assets):
        for name in os.listdir(assets):
            if name.endswith(".css"):
                with open(os.path.join(assets, name), encoding="utf-8") as fh:
                    chunks.append(fh.read())
    for dirpath, _dirnames, filenames in os.walk(SRC):
        for name in filenames:
            if name.endswith(".css"):
                with open(os.path.join(dirpath, name), encoding="utf-8") as fh:
                    chunks.append(fh.read())
    return "\n".join(chunks)


def css_tokens() -> set[str]:
    """Class names that actually have a rule in the stylesheets."""
    found: set[str] = set()
    for match in re.finditer(r"\.((?:\\.|[\w-])+)", collect_css()):
        raw = match.group(1)
        found.add(re.sub(r"\\(.)", r"\1", raw))
    return found


def source_tokens() -> dict[str, list[str]]:
    """candidate -> [file:line, …] for every colour-utility-looking token."""
    out: dict[str, list[str]] = {}
    for dirpath, _dirnames, filenames in os.walk(SRC):
        for name in sorted(filenames):
            if not name.endswith((".ts", ".tsx")):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, SRC).replace(os.sep, "/")
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    stripped = line.lstrip()
                    if stripped.startswith(("//", "*", "/*")):
                        continue
                    for token in TOKEN.findall(line):
                        if not token.startswith(PREFIXES):
                            continue
                        # a colour utility: prefix + a role-ish suffix
                        if len(token) < 5 or token.endswith("-"):
                            continue
                        # `border-radius:6px` is an inline CSS declaration
                        # (cssText strings), not a class: a real variant ends in
                        # another utility (`hover:bg-wash`, `[&_svg]:text-fg`).
                        tail = token.rsplit(":", 1)[-1]
                        if ":" in token and not tail.startswith(PREFIXES):
                            continue
                        out.setdefault(token, []).append(f"{rel}:{lineno}")
    return out


def main() -> int:
    css_dir = os.path.join(DIST, "assets")
    if not os.path.isdir(css_dir) or not any(n.endswith(".css") for n in os.listdir(css_dir)):
        print("FAIL: no built CSS in frontend/dist/assets — run ops/build_frontend.sh")
        return 1

    defined = css_tokens()
    used = source_tokens()

    print(f"css utility check: {len(used)} colour utilities used, "
          f"{len(defined)} class rules in the bundle")

    missing = []
    for token, places in sorted(used.items()):
        if token in ALLOWED:
            continue
        if token in defined:
            continue
        # Tailwind emits variants as part of the selector, so a match on the
        # bare token is not required; check the escaped form too.
        if any(escaped_selector(token) in d or d.endswith(token) for d in defined):
            continue
        missing.append((token, places))

    if missing:
        print(f"\n{len(missing)} utilities emit no CSS:")
        for token, places in missing:
            where = ", ".join(places[:3]) + ("…" if len(places) > 3 else "")
            print(f"  - {token}  ({where})")
        print("\nAdd the role to @theme in frontend/src/index.css, or stop using it.")
        return 1

    print("PASS — every colour utility used in src/ resolves to a rule.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
