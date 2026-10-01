"""Phase 5: brain-scoped route authorization (allow + deny) with signed JWKS.

    DATABASE_URL=<lab> python3 tests/test_route_authz.py
"""
import base64
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
URL = os.environ.get("DATABASE_URL", "")
assert "5434" in URL, "lab DB only"

os.environ["AUTH_MODE"] = "clerk"
os.environ["CLERK_JWKS_URL"] = "http://jwks.test/keys"
os.environ.setdefault("CLERK_ISSUER", "https://clerk.test")

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt as pyjwt
import psycopg
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
client = TestClient(app_module.app)

# org A: the workspace that owns company_brain (from the live backfill rows)
with psycopg.connect(URL, row_factory=psycopg.rows.dict_row) as conn, conn.cursor() as cur:
    org_a = cur.execute(
        "select org_id from brain_access where brain='company_brain' and org_id is not null limit 1"
    ).fetchone()["org_id"]
org_b = f"other_{uuid.uuid4().hex[:8]}"
hA = {"Authorization": f"Bearer {token(org_a, 'uA')}"}
hB = {"Authorization": f"Bearer {token(org_b, 'uB')}"}

r = client.get("/api/source", params={"name": "05_policy_SLA-credit-01.md", "dataset": "company_brain"}, headers=hA)
print("  source ALLOW (owner org):", r.status_code, "-> PASS" if r.status_code == 200 else f"FAIL {r.text[:80]}")
assert r.status_code == 200
r = client.get("/api/source", params={"name": "05_policy_SLA-credit-01.md", "dataset": "company_brain"}, headers=hB)
print("  source DENY (other org):", r.status_code, "-> PASS" if r.status_code in (403, 404) else "FAIL")
assert r.status_code in (403, 404)
r = client.get("/api/chats", params={"brain": "company_brain"}, headers=hA)
print("  chats ALLOW (owner org):", r.status_code, "-> PASS" if r.status_code == 200 else f"FAIL {r.text[:80]}")
assert r.status_code == 200
r = client.get("/api/chats", params={"brain": "company_brain"}, headers=hB)
print("  chats DENY (other org):", r.status_code, "-> PASS" if r.status_code in (403, 404) else "FAIL")
assert r.status_code in (403, 404)
r = client.get("/api/source", params={"name": "../../etc/passwd", "dataset": "company_brain"}, headers=hA)
print("  source traversal rejected:", r.status_code, "-> PASS" if r.status_code in (400, 404) else "FAIL")
assert r.status_code in (400, 404)
print("ROUTE AUTHZ (source/chats, allow+deny+traversal): PASS")
