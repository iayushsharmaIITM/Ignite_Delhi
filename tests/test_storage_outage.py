"""A storage outage is a 503, never a denial — and never an empty list.

Run standalone (no database at all: the connection is replaced with a stub):

    python3 tests/test_storage_outage.py

Prints one PASS/FAIL line per check and exits non-zero if any failed.

Why this file exists. `storage.brain_access()` caught every exception and returned
None, and `brain_allowed()` reads None as "no such brain" → 403. So during a Postgres
outage every authenticated user was told the brain they own does not exist — and the
`/api/source` path fell through to a 404 for the same reason. That behaviour was
recorded as a deliberate fail-closed decision (app.py SEC-2), and it stays fail CLOSED:
nothing is served while storage is down. What changes is the ANSWER — 503, retryable,
no claim about existence — because `AGENTS.md` already carries the rule "a storage
outage must surface as 503, never as an empty list", and because a user who is told
their own brain is unknown may well re-ingest it.

The three outcomes must stay distinguishable, which is the whole content of this tier:
  * query ran, no row            -> None  -> the existing uniform 403
  * query ran, row is someone else's -> 403, byte-identical to the missing-row denial
  * query FAILED                 -> raise -> 503, and mark_down() so `available()`
                                    stops promising postgres
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PROVIDER"] = "mock"
_url = os.environ.get("DATABASE_URL", "")
if _url and "5434" not in _url:
    raise SystemExit(
        "REFUSING: DATABASE_URL names a server that is not the lab (5434). This tier "
        "imports storage and app; it must not be pointed at the live database. Unset "
        "DATABASE_URL to run with no database at all, or use the lab.")
if not _url:
    os.environ["DATABASE_URL"] = "postgresql://kestrel:kestrel@127.0.0.1:1/kestrel"
os.environ["AUTH_MODE"] = "off"

import psycopg  # noqa: E402
import auth  # noqa: E402
import citations  # noqa: E402
import storage  # noqa: E402
import app as app_module  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(app_module.app)
FAILS = []
CHECKS = 0


def check(name, ok, detail=""):
    global CHECKS
    CHECKS += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else '  <- ' + detail}")
    if not ok:
        FAILS.append(name)


def boom(*a, **k):
    raise psycopg.OperationalError("connection refused (simulated outage)")


class _Cursor:
    """A cursor, and a context manager: `brain_access` opens it with `with`."""

    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        return self

    def fetchone(self):
        return self.row


class _Conn:
    """A connection that ran fine and found a row (or did not)."""

    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return _Cursor(self.row)


def with_conn(factory):
    saved = storage._conn
    storage._conn = factory
    return saved


def status_of(fn, *a, **k):
    try:
        fn(*a, **k)
        return None
    except HTTPException as exc:
        return exc.status_code


def identity_request(org="org-a", user="user-a"):
    req = types.SimpleNamespace(state=types.SimpleNamespace(identity={
        "org_id": org, "user_id": user}))
    return req


saved_conn = with_conn(boom)
try:
    # Force the cached verdict back to "healthy" so the mark_down assertion below
    # proves the outage flipped it, rather than reading a status that `import app`
    # already left unavailable against a database that does not exist.
    storage._status = {"storage": "postgres", "detail": ""}
    # --- 1. a failed query raises instead of masquerading as "no such brain" ---------
    raised = None
    try:
        storage.brain_access("company_brain")
    except Exception as exc:  # noqa: BLE001 - the type is the thing under test
        raised = exc
    check("a failed brain_access raises, it does not return None",
          isinstance(raised, storage.db_error), f"got {raised!r}")
    check("and it marks storage down so available() stops promising postgres",
          storage.status().get("storage") == "unavailable",
          f"status is {storage.status()}")
    check("the reason names the operation, for the operator",
          "brain_access" in str(storage.status().get("detail") or ""),
          f"detail is {storage.status().get('detail')!r}")

    # --- 2. brain_allowed: outage is 503, a missing/foreign brain is still that 403 --
    real_auth = auth.active
    auth.active = lambda: True
    try:
        code = status_of(app_module.brain_allowed, identity_request(), "company_brain")
        check("an outage answers 503, not 'Unknown brain'", code == 503, f"got {code}")

        detail = ""
        try:
            app_module.brain_allowed(identity_request(), "company_brain")
        except HTTPException as exc:
            detail = str(exc.detail)
        check("and says it is unavailable and retryable, not nonexistent",
              "unavailable" in detail.lower(), f"detail {detail!r}")

        storage._conn = lambda *a, **k: _Conn(None)
        code = status_of(app_module.brain_allowed, identity_request(), "no-such-brain")
        check("a genuinely unknown brain still answers the uniform 403",
              code == 403, f"got {code}")

        storage._conn = lambda *a, **k: _Conn(
            {"brain": "b", "org_id": "someone-else", "created_by": "other",
             "is_shared": False, "status": "ready"})
        code = status_of(app_module.brain_allowed, identity_request(), "b")
        check("a foreign brain still answers the SAME 403, so existence cannot be probed",
              code == 403, f"got {code}")

        storage._conn = lambda *a, **k: _Conn(
            {"brain": "b", "org_id": "org-a", "created_by": "someone",
             "is_shared": False, "status": "ready"})
        code = status_of(app_module.brain_allowed, identity_request(org="org-a"), "b")
        check("the owning org is still allowed through", code is None, f"got {code}")

        # Auth-off behaviour must not move at all: it is the verification seam.
        auth.active = lambda: False
        storage._conn = boom
        code = status_of(app_module.brain_allowed, identity_request(), "anything")
        check("with auth off an outage does not start answering 403s/503s",
              code is None, f"got {code}")
    finally:
        auth.active = real_auth
finally:
    storage._conn = saved_conn

# --- 3. /api/source: a durable lookup that FAILS is 503, not a 404 -------------------
saved_durable = citations.durable_source


def failing_durable(*a, **k):
    raise psycopg.OperationalError("connection refused (simulated outage)")


citations.durable_source = failing_durable
try:
    r = client.get("/api/source", params={"name": "own_file.md", "dataset": "acme-ops"})
    outcome = r.status_code
    blurb = f"{r.status_code} {r.text[:80]}"
except Exception as exc:  # noqa: BLE001 - an escaping driver error IS the failure
    outcome = None
    blurb = f"the {type(exc).__name__} escaped the route instead of becoming a status"
check("a source lookup during an outage is 503, not 404 and not another document",
      outcome == 503, blurb)
citations.durable_source = saved_durable

# --- 4. the answer path must NOT die with the user: unresolved is enough -------------
saved_rows = citations._rows
citations._rows = boom
try:
    check("a durable reference lookup that fails yields None (unresolved), not a raise",
          citations._durable_reference("acme", "deadbeef") is None)
finally:
    citations._rows = saved_rows

print("STORAGE OUTAGE (503 is not a denial):", "FAIL" if FAILS else "PASS")
if FAILS:
    print(f"  {len(FAILS)} of {CHECKS} checks failed: {', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
