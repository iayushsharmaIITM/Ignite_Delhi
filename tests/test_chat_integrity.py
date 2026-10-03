"""Round 2 (CH-1..CH-9): chat integrity — no silent truncation, no
resurrection, honest deletes, authorized filing, unbreakable payloads.

    DATABASE_URL=<lab 5434> python3 tests/test_chat_integrity.py

Why this file exists: the previous session's audit found that a chat save
rewrote `turns` wholesale while the client only ever sent its last 60 turns,
that a deleted chat could be re-created by any stale tab, and that DELETE
answered 200 for a delete that removed nothing. Each rule below is the
regression test for one of those; they fail loudly if the guard is removed.

Every row this file writes is `itest-*` and is deleted again in the finally.
"""
import base64
import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
URL = os.environ.get("DATABASE_URL", "")
assert "5434" in URL, "lab DB only — this file writes rows"

os.environ["AUTH_MODE"] = "clerk"
os.environ["CLERK_JWKS_URL"] = "http://jwks.test/keys"
os.environ.setdefault("CLERK_ISSUER", "https://clerk.test")

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt as pyjwt
import psycopg
from psycopg.rows import dict_row
from fastapi.testclient import TestClient

priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
pn = priv.public_key().public_numbers()


def b64(n):
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


jwks = {"keys": [{"kty": "RSA", "alg": "RS256", "use": "sig", "kid": "t",
                  "n": b64(pn.n), "e": b64(pn.e)}]}
import auth
auth.inject_jwks_for_test(os.environ["CLERK_JWKS_URL"], jwks)


def token(org_id, user_id):
    return pyjwt.encode({"sub": user_id, "iss": os.environ["CLERK_ISSUER"],
                         "exp": time.time() + 600, "o": {"id": org_id}},
                        priv, algorithm="RS256", headers={"kid": "t"})


import storage
import app as app_module

client = TestClient(app_module.app)

with psycopg.connect(URL, row_factory=dict_row) as conn, conn.cursor() as cur:
    org_a = cur.execute(
        "select org_id from brain_access where brain='company_brain' "
        "and org_id is not null limit 1").fetchone()["org_id"]
hA = {"Authorization": f"Bearer {token(org_a, 'itest-user')}"}
hB = {"Authorization": f"Bearer {token('other_org_' + uuid.uuid4().hex[:6], 'itest-user-b')}"}

FAILS = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(label)


def turns_of(n, tag="t"):
    return [{"role": "user", "text": f"{tag}{i}" , "at": 1700000000000 + i * 1000}
            if i % 2 == 0 else
            {"role": "bot", "text": f"answer {i}", "sources": [], "steps": [{"label": "s"}],
             "workedMs": 1200 + i, "at": 1700000000000 + i * 1000}
            for i in range(n)]


def save(cid, turns, trim=False, headers=hA, brain="company_brain"):
    return client.post("/api/chats", params={"brain": brain}, headers=headers,
                       json={"id": cid, "title": "itest", "turns": turns, "trim": trim})


def read(cid, headers=hA):
    r = client.get(f"/api/chats/{cid}", headers=headers)
    return r


made = []
try:
    print("[CH-1] a shorter save may not delete stored history")
    cid = "itest-trim-" + uuid.uuid4().hex[:8]
    made.append(cid)
    r = save(cid, turns_of(6))
    check("full save lands", r.status_code == 200, f"{r.status_code} {r.text[:60]}")
    r = save(cid, turns_of(3))
    check("stale 3-turn window is REFUSED (409)", r.status_code == 409,
          f"{r.status_code} {r.text[:70]}")
    got = read(cid).json()["chat"]["turns"]
    check("history survived the refused save", len(got) == 6, f"{len(got)} turns")
    r = save(cid, turns_of(3), trim=True)
    check("a DECLARED trim is accepted", r.status_code == 200, r.text[:70])
    got = read(cid).json()["chat"]["turns"]
    check("trimmed save wrote the new window", len(got) == 3, f"{len(got)} turns")

    print("[CH-5] a restored turn keeps its own time on re-save")
    cid = "itest-at-" + uuid.uuid4().hex[:8]
    made.append(cid)
    save(cid, turns_of(2))
    first = read(cid).json()["chat"]["turns"][0]
    # the client sends back exactly what the server gave it (an ISO string);
    # _ts used to answer None and COALESCE fell through to now()
    again = [dict(first), {"role": "bot", "text": "new answer"}]
    r = save(cid, again, trim=True)
    check("re-save with an ISO `at` accepted", r.status_code == 200, r.text[:70])
    kept = read(cid).json()["chat"]["turns"][0]
    check("`at` round-tripped unchanged", str(kept["at"]) == str(first["at"]),
          f"{first['at']} -> {kept['at']}")

    print("[CH-2] a deleted chat stays deleted")
    cid = "itest-gone-" + uuid.uuid4().hex[:8]
    made.append(cid)
    save(cid, turns_of(2))
    r = client.delete(f"/api/chats/{cid}", headers=hA)
    check("delete reports success", r.status_code == 200 and r.json()["ok"] is True,
          f"{r.status_code} {r.text[:60]}")
    r = save(cid, turns_of(2))
    check("resurrecting a deleted id is refused (410)", r.status_code == 410,
          f"{r.status_code} {r.text[:70]}")
    with psycopg.connect(URL, row_factory=dict_row) as conn, conn.cursor() as cur:
        n = cur.execute("select count(*) as n from chats where id = %s", (cid,)).fetchone()["n"]
    check("no chats row was re-created", n == 0, f"{n} rows")

    print("[CH-3] DELETE tells the truth")
    r = client.delete("/api/chats/itest-never-existed-" + uuid.uuid4().hex[:8], headers=hA)
    check("unknown id is 404, not 200 ok:false", r.status_code == 404,
          f"{r.status_code} {r.text[:60]}")

    print("[CH-4/CH-6] filing a chat is a brain access")
    cid = "itest-brain-" + uuid.uuid4().hex[:8]
    r = save(cid, turns_of(2), brain="itest_not_a_brain")
    check("unknown brain refused (403/404)", r.status_code in (403, 404),
          f"{r.status_code} {r.text[:60]}")
    if r.status_code == 200:
        made.append(cid)

    print("[CH-7] the list says how much it left out")
    r = client.get("/api/chats", params={"limit": 1}, headers=hA)
    d = r.json()
    check("total + truncated are reported", "total" in d and "truncated" in d,
          json.dumps({k: d.get(k) for k in ("returned", "total", "truncated", "limit")}))
    check("total counts beyond the page",
          int(d.get("total") or 0) >= int(d.get("returned") or 0),
          f"returned={d.get('returned')} total={d.get('total')}")

    print("[CH-9] a bad field cannot 500 the save")
    cid = "itest-bad-" + uuid.uuid4().hex[:8]
    made.append(cid)
    r = save(cid, [{"role": "bot", "text": "hi", "workedMs": "abc"}])
    check("non-numeric workedMs does not 500", r.status_code == 200,
          f"{r.status_code} {r.text[:60]}")
    r = save(cid + "-x", ["not an object"])
    check("a non-object turn is a 422, not a 500", r.status_code == 422,
          f"{r.status_code} {r.text[:60]}")
    r = save(cid + "-y", [{"role": "bot", "text": "hi", "steps": ["x" * 600_000]}])
    check("oversized turn metadata is 413", r.status_code == 413,
          f"{r.status_code} {r.text[:60]}")
    r = client.post("/api/chats", headers=hA, content=b"[1,2,3]")
    check("a JSON array body is a 400, not a 500", r.status_code == 400,
          f"{r.status_code} {r.text[:60]}")

    print("[CH-8] storage failure degrades as declared")
    check("db_error is exported for the routes", hasattr(storage, "db_error"))
    check("mark_down exists", callable(getattr(storage, "mark_down", None)))
finally:
    with psycopg.connect(URL) as conn, conn.cursor() as cur:
        for cid in made:
            cur.execute("DELETE FROM turns WHERE chat_id = %s", (cid,))
            cur.execute("DELETE FROM chats WHERE id = %s", (cid,))
            cur.execute("DELETE FROM deleted_chats WHERE id = %s", (cid,))
        cur.execute("DELETE FROM chats WHERE id LIKE 'itest-%'")
        cur.execute("DELETE FROM turns WHERE chat_id LIKE 'itest-%'")
        cur.execute("DELETE FROM deleted_chats WHERE id LIKE 'itest-%'")
    left = client.get("/api/chats", params={"limit": 500}, headers=hA).json()["chats"]
    leftovers = [c["id"] for c in left if str(c["id"]).startswith("itest-")]
    if leftovers:
        print("  WARN: test rows left behind:", leftovers)
    print(f"cleanup: {len(made)} chats removed")

print()
if FAILS:
    print(f"chat integrity: {len(FAILS)} FAILING -> {FAILS}")
    sys.exit(1)
print("chat integrity: all checks pass")
