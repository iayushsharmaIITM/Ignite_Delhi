"""Source precedence: a citation opens the brain's own document, never a demo file.

Run standalone (no database, no provider, no browser — safe for the CI fast lane):

    python3 tests/test_source_precedence.py

Prints one PASS/FAIL line per check and exits non-zero if any failed.

Why this file exists. `/api/source` used to look up `corpus/<filename>` on disk FIRST and
only then consult the authorised brain's own tables (app.py:2228-2233 ran before the
durable lookup at :2247 and the tenant read at :2251-2257). `corpus/` is shared by every
dataset and its files are named like a real document
(`05_policy_SLA-credit-01.md`), so a customer who uploaded a file with a corpus filename
clicked a citation and got Kestrel's demo text — a confidently wrong source, which is the
one thing the product's invariant forbids.

The rules these checks defend:
  * A non-demo dataset never reads `corpus/`. If the tenant's own tables have no such
    document, the answer is 404 "no source document", not a substitution.
  * The demo brain keeps its order and its speed. It resolves from `corpus/` first and
    must not touch the durable path at all — the tenant map takes ~20s to resolve and the
    guard that avoids it predates this file.
  * Authz still runs before any of it (covered by tests/test_route_authz.py).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Hermetic before anything is imported, for the two reasons tests/test_phatic.py states:
# `import app` runs storage.init(), so a DATABASE_URL that is already in the environment
# must name the lab on 5434 or this refuses to run; and PROVIDER decides whether a read
# goes to fixtures or to the live tenant.
os.environ["PROVIDER"] = "mock"
os.environ["AUTH_MODE"] = "off"
_url = os.environ.get("DATABASE_URL", "")
if _url and "5434" not in _url:
    raise SystemExit(
        "REFUSING: DATABASE_URL names a server that is not the lab (5434). This tier "
        "imports app.py, which runs storage.init(); it must not be pointed at the live "
        "database. Unset DATABASE_URL to run with no database at all, or use the lab.")
if not _url:
    os.environ["DATABASE_URL"] = "postgresql://kestrel:kestrel@127.0.0.1:1/kestrel"

import citations                    # noqa: E402
import app as app_module            # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(app_module.app)
DEMO = app_module.DEMO_DATASET
# A file that really is in corpus/, read here and never written.
CORPUS_NAME = "05_policy_SLA-credit-01.md"
CORPUS_TEXT = open(os.path.join(app_module.HERE, "corpus", CORPUS_NAME),
                   encoding="utf-8").read()
# What the tenant says its own document holds. Deliberately shares nothing with the
# corpus file, so a corpus win is unmistakable in the response.
TENANT_TEXT = "ACME internal escalation policy, revision 4. Nothing like the demo file."

FAILS = []
CHECKS = 0


def check(name, ok, detail=""):
    global CHECKS
    CHECKS += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else '  <- ' + detail}")
    if not ok:
        FAILS.append(name)


def get_source(dataset, name):
    return client.get("/api/source", params={"name": name, "dataset": dataset})


# --- 1. the demo brain keeps reading corpus/, and keeps not touching durable ---------
real_durable = citations.durable_source
real_data_id_for = citations.data_id_for
calls = []
citations.durable_source = lambda *a, **k: calls.append(a) or None
r = get_source(DEMO, CORPUS_NAME)
body = r.json() if r.status_code == 200 else {}
check("demo brain still serves the corpus file",
      r.status_code == 200 and body.get("source") == "corpus",
      f"{r.status_code} {str(body)[:80]}")
check("demo corpus text is the corpus file", body.get("text") == CORPUS_TEXT,
      "text differs")
check("demo path never reaches the durable lookup (the ~20s guard)", not calls,
      f"durable_source called with {calls[:1]}")

# --- 2. the bug: a tenant document that shares a corpus filename --------------------
citations.durable_source = lambda ds, fn, *a, **k: TENANT_TEXT
r = get_source("acme-ops", CORPUS_NAME)
body = r.json() if r.status_code == 200 else {}
check("tenant brain is asked before the corpus is read",
      r.status_code == 200 and body.get("source") == "durable",
      f"{r.status_code} got source={body.get('source')!r}")
check("tenant gets its own text, not the demo file",
      body.get("text") == TENANT_TEXT,
      f"returned the corpus text ({len(body.get('text') or '')} chars)")

# --- 3. a tenant with no such document is a 404, never a substitution ---------------
citations.durable_source = lambda ds, fn, *a, **k: None
citations.data_id_for = lambda ds, fn: None
r = get_source("acme-ops", CORPUS_NAME)
check("unknown tenant document 404s instead of showing demo text",
      r.status_code == 404,
      f"{r.status_code} {r.text[:80]}")
citations.durable_source = real_durable
citations.data_id_for = real_data_id_for

# --- 4. the shape of the honest answer for the demo ---------------------------------
r = get_source(DEMO, "does_not_exist.md")
check("demo miss is a 404, not a fallthrough to the tenant", r.status_code == 404,
      f"{r.status_code} {r.text[:80]}")

# --- 5. the version id travels from the citation to the lookup ----------------------
seen = {}


def record_durable(ds, fn, dv=None, *a, **k):
    seen.update({"ds": ds, "fn": fn, "dv": dv})
    return TENANT_TEXT


citations.durable_source = record_durable
r = client.get("/api/source", params={"name": "own_file.md", "dataset": "acme-ops",
                                      "document_version_id": "a1b2c3d4-0000-1111-2222-333344445555"})
check("a citation with a version id passes it to the lookup",
      r.status_code == 200 and seen.get("dv") == "a1b2c3d4-0000-1111-2222-333344445555",
      f"{r.status_code} looked up {seen}")
r = client.get("/api/source", params={"name": "own_file.md", "dataset": "acme-ops",
                                      "document_version_id": "../../corpus/01_x.md"})
check("a malformed version id is refused, never downgraded to 'newest'",
      r.status_code == 400, f"{r.status_code} {r.text[:80]}")
citations.durable_source = real_durable

print("SOURCE PRECEDENCE (corpus is the demo's, not everyone's):",
      "FAIL" if FAILS else "PASS")
if FAILS:
    print(f"  {len(FAILS)} of {CHECKS} checks failed: {', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
