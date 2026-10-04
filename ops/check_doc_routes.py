#!/usr/bin/env python3
"""Fail when a living document tells a reader to run a script that is not in the tree.

ops/doc_health.sh exists because a stale instruction is not cosmetic — an agent
obeys it. It checked seven things by hand and never asked the one question that
catches this class: does the command a document prints resolve to a file? Three
rounds of deletions (battery.py, check_ui.py, contract_test.py) each left a
document route behind them and the gate stayed green, because a hand-written
assertion can only test what its author thought to write.

Scope comes from docs/INDEX.md's Living table, so the document map decides what is
live and this script does not need a second list to keep in sync.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "docs", "INDEX.md")

# Command-shaped references only. Prose that names a file without telling the
# reader to execute it is not a route an agent will follow.
CMD = re.compile(r"(?:python3|python|bash|\./)\s+([A-Za-z0-9_./-]+\.(?:py|sh))\b")
LIVING = re.compile(r"^## Living.*?(?=\n## )", re.S | re.M)
TICKED = re.compile(r"`([^`]+\.md)`")

# A line describing a retirement is not an instruction to run the thing that is
# gone. BUGS_AUDIT.md quotes "`python3 check_ui.py` scored 16/16" precisely to say
# that claim was once false; flagging that would train everyone to skip this gate's
# output. Narrow vocabulary, applied per line, so a genuine route row in README
# still fails.
ABOUT_REMOVAL = re.compile(
    r"(?i)\b(delet\w+|retir\w+|remov\w+|superseded|no longer|used to|formerly|"
    r"advertis\w+|claimed|claim|stale|obsolete)\b")

# PROGRESS.md is an execution log. Everything below its newest entry is a dated
# record of what was run at the time, and rewriting those entries to match today's
# tree would destroy the record; only the newest entry is advice to the reader.
LOGS = {"PROGRESS.md"}


def living_docs():
    """The set from docs/INDEX.md, or None if the map cannot be read.

    None is a failure, not an empty list: a gate that silently finds nothing to
    check is the same false green this file was written to stop.
    """
    text = open(INDEX, encoding="utf-8").read()
    block = LIVING.search(text)
    if not block:
        return None
    return sorted(set(TICKED.findall(block.group(0))))


def newest_entry(lines):
    seen = False
    for i, line in enumerate(lines, 1):
        if line.startswith("## "):
            if seen:
                return i
            seen = True
    return len(lines)


def resolves(target):
    bare = target.lstrip("./")
    return any(os.path.exists(os.path.join(ROOT, p, bare))
               for p in (".", "ops", "frontend", "docs"))


def main():
    docs = living_docs()
    if docs is None:
        print("  cannot read the Living table from docs/INDEX.md — nothing was checked")
        return 1
    bad = []
    for doc in docs:
        path = os.path.join(ROOT, doc)
        if not os.path.exists(path):
            bad.append((doc, 0, "the document itself is missing"))
            continue
        lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
        limit = newest_entry(lines) if os.path.basename(doc) in LOGS else len(lines)
        for i, line in enumerate(lines[:limit], 1):
            if ABOUT_REMOVAL.search(line):
                continue
            for target in CMD.findall(line):
                if not resolves(target):
                    bad.append((doc, i, target))
    if bad:
        for doc, line, target in bad:
            print(f"  {doc}:{line} -> {target} (no such file)")
        print(f"  {len(bad)} document route(s) lead nowhere")
        return 1
    print("  every command a living document prints resolves to a file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
