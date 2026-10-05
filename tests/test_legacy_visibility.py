"""Characterisation, not a security gate: what today's tenancy rule actually shows.

Run standalone (no database):

    python3 tests/test_legacy_visibility.py

Prints one PASS/FAIL line per check and exits non-zero if any failed.

Ayush's call on the tenancy items in the incoming brief (B05/B06/X-USAGE) was
"demonstrate, change nothing", so this file changes nothing. It pins the CURRENT rules
in `_owner_clause` and `usage_summary` so that changing them later is a decision someone
made, not a line someone edited. Every PASS below is a description of visibility that
exists today — none of it is a claim that the behaviour is right.

The three open questions, recorded in docs/FIX_LOG.md under NEEDS DECISION:
  1. Are legacy rows with both owner columns NULL demo data, or somebody's private data?
     Today: visible to EVERY authenticated identity.
  2. Should an organisation-owned row follow org membership or its creator? Today:
     either one is enough (OR), so a former member who created a chat keeps reading it
     inside an org they have left.
  3. Should a brain that has no brain_access row at all appear in a scoped caller's
     usage? Today: yes, by the grandfathering arm in usage_summary's scope.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_url = os.environ.get("DATABASE_URL", "")
if _url and "5434" not in _url:
    raise SystemExit(
        "REFUSING: DATABASE_URL names a server that is not the lab (5434).")
os.environ.setdefault("AUTH_MODE", "off")
os.environ.setdefault("PROVIDER", "mock")

import storage  # noqa: E402

FAILS = []
CHECKS = 0


def check(name, ok, detail=""):
    global CHECKS
    CHECKS += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else '  <- ' + detail}")
    if not ok:
        FAILS.append(name)


a = storage._owner_clause("org-a", "user-a")
b = storage._owner_clause("org-b", "user-b")

# 1. auth-off mode: no predicate at all, which is the single-user verification seam.
check("with no identity there is no predicate (auth-off mode is unchanged)",
      storage._owner_clause(None, None) == ("", []),
      repr(storage._owner_clause(None, None)))

# 2. the grandfathering arm, in the words the database will run.
check("an authenticated identity is given the legacy NULL/NULL arm",
      "(org_id IS NULL AND created_by IS NULL)" in a[0], a[0])
check("so TWO DIFFERENT orgs both match a legacy row (today, by design)",
      "(org_id IS NULL AND created_by IS NULL)" in b[0] and a[0] == b[0],
      f"a={a[0]!r} b={b[0]!r}")

# 3. org OR creator, not org AND creator.
check("membership OR creator is enough to read a stamped row",
      a[0].count(" OR ") == 2 and " AND " not in a[0].replace(
          "(org_id IS NULL AND created_by IS NULL)", ""), a[0])

# 4. the parameters line up with the placeholders — the class of defect that turns a
#    predicate into a 500 or, worse, into a clause that filters on the wrong column.
check("one placeholder per bound parameter, in org-then-creator order",
      a[0].count("%s") == len(a[1]) == 2 and a[1] == ["org-a", "user-a"], repr(a[1]))

# 5. usage: a brain with no access row is still counted for a scoped caller.
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "storage.py"), encoding="utf-8").read()
usage = re.search(r"def usage_summary\(.*?^def ", src, re.S | re.M)
check("a scoped usage summary still includes brains nobody registered",
      bool(usage) and "brain NOT IN (SELECT brain FROM brain_access)" in usage.group(0),
      "the grandfathering arm moved or was removed — if this was deliberate, this file "
      "is the thing that has to change with it")

print("LEGACY VISIBILITY (characterisation of today's rule):", "FAIL" if FAILS else "PASS")
if FAILS:
    print(f"  {len(FAILS)} of {CHECKS} checks failed: {', '.join(FAILS)}")
print("  NOTE: not a security gate, and not an end-to-end visibility test — with no")
print("        database in the CI fast lane this reads the PREDICATE that decides who")
print("        sees what, which is where the rule lives. A PASS describes today; it is")
print("        not an approval of it.")
sys.exit(1 if FAILS else 0)
