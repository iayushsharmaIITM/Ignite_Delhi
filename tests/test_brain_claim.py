"""M4: brain creation is exclusive. The name is claimed before the work starts,
a failed create gives the claim back, and two concurrent creates cannot both
think they won.

    DATABASE_URL=<lab 5434> python3 tests/test_brain_claim.py

Why it is worth the plumbing: `cognee_cloud.exists(name)` can only report the
past. Two requests that both hear "does not exist" both ingest, and the
ownership row then credits the finished dataset to whoever inserted first — so
the other tenant's documents end up inside a brain it can no longer reach, with
no error anywhere in the log. Only a reservation, not an observation, prevents
that, so this file drives the race for real.

Runs against the LAB database only (it asserts 5434) and deletes every row it
creates. Nothing here touches the tenant: PROVIDER is forced to cloud only to
pass the route's gate, and the ingest calls are stubbed.
"""
import base64
import concurrent.futures
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
URL = os.environ.get("DATABASE_URL", "")
assert "5434" in URL, "lab DB only — this file writes ownership rows"

os.environ["AUTH_MODE"] = "clerk"
os.environ["CLERK_JWKS_URL"] = "http://jwks.test/keys"
os.environ.setdefault("CLERK_ISSUER", "https://clerk.test")

from cryptography.hazmat.primitives.asymmetric import rsa
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


import app as app_module
import memory_layer
import cognee_cloud
import citations
import storage

client = TestClient(app_module.app)

# The route refuses non-cloud providers; the ingest calls are stubbed below so
# nothing leaves this process. `exists()` is the one stub that has to be
# honest-ish: it reports a brain as existing once its claim has been flipped to
# 'ready', which is what lets the append and duplicate-name paths behave the way
# they would against a real tenant.
memory_layer.PROVIDER = "cloud"


def _exists(name: str) -> bool:
    with psycopg.connect(URL, row_factory=dict_row) as conn, conn.cursor() as cur:
        row = cur.execute(
            "SELECT status FROM brain_access WHERE brain = %s", (name,)
        ).fetchone()
    return bool(row and row["status"] == "ready")


cognee_cloud.exists = _exists
citations.record_upload = lambda *a, **k: None


async def _remember_noop(text, name, filename=None):
    return {"ok": True}


memory_layer.remember = _remember_noop

FAILS = []
made: list[str] = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"   [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(label)


def newname():
    n = "itest_" + uuid.uuid4().hex[:10]
    made.append(n)
    return n


def upload(name, headers):
    return client.post(
        "/api/brains",
        headers=headers,
        data={"name": name},
        files=[("files", ("policy.md", "# Policy\n\nThe renewal is at risk.", "text/markdown"))],
    )


def rows(brain):
    with psycopg.connect(URL, row_factory=dict_row) as conn, conn.cursor() as cur:
        return cur.execute(
            "SELECT org_id, created_by, status FROM brain_access WHERE brain = %s",
            (brain,),
        ).fetchall()


ORG_A, ORG_B = "itest_org_a", "itest_org_b"
hA = {"Authorization": f"Bearer {token(ORG_A, 'u_a')}"}
hB = {"Authorization": f"Bearer {token(ORG_B, 'u_b')}"}

try:
    print("[storage] the claim primitive")
    n = newname()
    check("an unclaimed name is claimable",
          storage.claim_brain(n, ORG_A, "u_a") == "claimed")
    check("the row exists as 'creating'",
          rows(n) and rows(n)[0]["status"] == "creating", str(rows(n)))
    check("a second identity is refused while it is in flight",
          storage.claim_brain(n, ORG_B, "u_b") == "taken")
    check("the creator may re-enter its own claim",
          storage.claim_brain(n, ORG_A, "u_a") == "retry")
    storage.mark_brain_ready(n)
    check("success flips the row to 'ready'",
          rows(n)[0]["status"] == "ready", str(rows(n)))
    check("a ready brain owned by another identity stays refused",
          storage.claim_brain(n, ORG_B, "u_b") == "taken")
    check("its own owner reads it as 'owned'",
          storage.claim_brain(n, ORG_A, "u_a") == "owned")
    storage.release_brain_claim(n, ORG_A, "u_a")
    check("release does not delete a READY brain's row (only claims)",
          len(rows(n)) == 1, str(rows(n)))
    storage.unregister_brain(n)

    print("[route] two creates of the same name, at once")
    n = newname()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        ra, rb = list(pool.map(lambda h: upload(n, h), [hA, hB]))
    codes = sorted([ra.status_code, rb.status_code])
    check("exactly one create succeeds and one is refused",
          codes == [200, 409], f"{ra.status_code} / {rb.status_code}")
    owners = rows(n)
    check("one ownership row, and it says ready",
          len(owners) == 1 and owners[0]["status"] == "ready", str(owners))
    winning_org = owners[0]["org_id"]
    loser = ra if ra.status_code == 409 else rb
    check("the refused caller is told to retry or rename, not silently merged",
          b"another name" in loser.content or b"right now" in loser.content,
          loser.content[:120].decode(errors="replace"))
    check("the winner is the recorded owner", winning_org in (ORG_A, ORG_B),
          str(winning_org))
    check("the losing identity cannot read the winner's brain",
          client.get("/api/stats", params={"dataset": n}, headers=hB
                     if winning_org == ORG_A else hA).status_code == 403)

    print("[route] a failed create gives the name back")
    n = newname()
    import documents
    original = documents.extract_many
    documents.extract_many = lambda payload: ([], [{"name": "policy.md", "error": "unreadable"}])
    try:
        r = upload(n, hA)
    finally:
        documents.extract_many = original
    check("the unreadable upload is refused with 400", r.status_code == 400,
          f"{r.status_code} {r.text[:90]}")
    check("no claim survives the failure", rows(n) == [], str(rows(n)))
    check("another identity can now take that name",
          storage.claim_brain(n, ORG_B, "u_b") == "claimed")
    storage.unregister_brain(n)

    print("[route] append to an existing brain still works")
    n = newname()
    r1 = upload(n, hA)
    check("first create succeeded", r1.status_code == 200, r1.text[:90])
    r2 = client.post("/api/brains", headers=hA, data={"name": n, "append": "true"},
                     files=[("files", ("more.md", "# More", "text/markdown"))])
    check("explicit append is accepted", r2.status_code == 200, r2.text[:90])
    r3 = upload(n, hA)
    check("an implicit second create is refused (unchanged behaviour)",
          r3.status_code == 409, r3.text[:90])

finally:
    with psycopg.connect(URL) as conn, conn.cursor() as cur:
        for n in made:
            cur.execute("DELETE FROM brain_access WHERE brain = %s", (n,))
        cur.execute("DELETE FROM brain_access WHERE brain LIKE 'itest_%'")
    print(f"cleanup: {len(made)} brain names removed from brain_access")

print()
if FAILS:
    print(f"brain claim: {len(FAILS)} FAILING -> {FAILS}")
    sys.exit(1)
print("brain claim: all checks pass — M4 is closed")
