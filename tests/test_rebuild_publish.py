"""A REBUILD job must be able to publish (E13 / A-58).

Run standalone (no database, no tenant, no browser):

    python3 tests/test_rebuild_publish.py

Prints one PASS/FAIL line per check and exits non-zero if any failed.

What was reproduced, and what it cost to find. `stage_rebuild()` deliberately leaves
the brain alone — the old generation stays ACTIVE and the brain stays READY until the
new generation verifies, so a failed rebuild cannot leave a company brain broken (that
is the spec, and _fail() honours it: it only moves a brain to FAILED while it is
CREATING). The publish fence did not get the memo:

    ok = (brain["state"] == "CREATING" and ...)          # lifecycle.py:438
    if verified == 0 or brain["state"] != "CREATING":     # recovery, :601

Both fences therefore describe a CREATE. A REBUILD, whose brain is READY by
construction, could not pass either one — so it ended in
RECONCILIATION_REQUIRED/PUBLISH_FENCED in the job path and in
RECOVERY:INVENTORY_INCOMPLETE in the recovery path, and no rebuild could ever publish.

The rule is now one predicate, `_publishable(state, is_rebuild)`, and this tier pins
both halves of it: a rebuild publishes from READY, and a CREATE still refuses to
publish anything that is not CREATING — that refusal is the double-publish guard and
must not be loosened on the way to fixing the other bug.

The last two checks read lifecycle.py's own source. They exist because the fix is a
guard that appears in two places; a future edit that re-opens either one with a literal
`== "CREATING"` would silently reintroduce E13 in a file no test otherwise executes.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_url = os.environ.get("DATABASE_URL", "")
if _url and "5434" not in _url:
    raise SystemExit(
        "REFUSING: DATABASE_URL names a server that is not the lab (5434). This tier "
        "imports lifecycle; it must not be pointed at the live database.")
os.environ.setdefault("AUTH_MODE", "off")
os.environ.setdefault("PROVIDER", "mock")

import lifecycle  # noqa: E402

FAILS = []
CHECKS = 0
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(name, ok, detail=""):
    global CHECKS
    CHECKS += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else '  <- ' + detail}")
    if not ok:
        FAILS.append(name)


if not hasattr(lifecycle, "_publishable"):
    check("lifecycle._publishable exists as the one publish rule", False,
          "the fences compare brain state inline, which is what made every REBUILD "
          "unpublishable (E13)")
else:
    # A CREATE may only publish a brain it started: CREATING is the proof that nobody
    # else has already published it.
    check("a CREATE still publishes from CREATING",
          lifecycle._publishable("CREATING", False) is True)
    check("a CREATE refuses a brain that is already READY (the double-publish guard)",
          lifecycle._publishable("READY", False) is False)
    check("a CREATE refuses FAILED", lifecycle._publishable("FAILED", False) is False)

    # A REBUILD starts from a live brain. Requiring CREATING there is the bug.
    check("a REBUILD publishes from READY",
          lifecycle._publishable("READY", True) is True)
    check("a REBUILD does NOT publish a brain that is still being created",
          lifecycle._publishable("CREATING", True) is False,
          "two jobs publishing the same brain is how generations get lost")
    check("a REBUILD does not publish FAILED",
          lifecycle._publishable("FAILED", True) is False)

src = open(os.path.join(HERE, "lifecycle.py"), encoding="utf-8").read()
# Read the file with the helper itself blanked out, so what is left is the call sites.
helper = re.search(r"def _publishable\(.*?(?=^def |\Z)", src, re.S | re.M)
outside = src[:helper.start()] + src[helper.end():] if helper else src
inline = [m.group(0) for m in re.finditer(r'[A-Za-z_"\[\] ]{0,24}[!=]=\s*"CREATING"', outside)]
check("no publish fence compares brain state inline any more", not inline,
      f"found {inline}")
def body_of(name):
    """One top-level function's source, so a guard cannot hide in the wrong one."""
    m = re.search(rf"^def {name}\(.*?(?=^def |\Z)", src, re.S | re.M)
    return m.group(0) if m else ""


for fn in ("process_job", "recover_reconciliation"):
    check(f"the fence inside {fn} asks the one rule",
          "_publishable(" in body_of(fn),
          "this is the fence that rejected every rebuild; a literal comparison "
          "re-opened here would put A-58 back with no tier to catch it")

print("REBUILD PUBLISH FENCE (A-58):", "FAIL" if FAILS else "PASS")
if FAILS:
    print(f"  {len(FAILS)} of {CHECKS} checks failed: {', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
