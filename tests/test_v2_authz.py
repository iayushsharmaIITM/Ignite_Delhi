"""Phase 4.6: v2 workspace authorization, allow AND deny directions.

Runs the real app in-process (TestClient) with AUTH_MODE=clerk and an injected
JWKS (auth.py test seam). Two orgs; org A creates a v2 brain; org A may read
the job, org B gets 403 with the workspace message.

    DATABASE_URL=<lab> python3 tests/test_v2_authz.py
"""
import base64
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

URL = os.environ.get("DATABASE_URL", "")
assert "5434" in URL, "lab DB only"

os.environ["AUTH_MODE"] = "clerk"
os.environ["KESTREL_JOBS_V2"] = "1"
os.environ["CLERK_JWKS_URL"] = "http://jwks.test/keys"
if "CLERK_ISSUER" not in os.environ:
    os.environ["CLERK_ISSUER"] = "https://clerk.test"

import cryptography
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt as pyjwt
import psycopg
from fastapi.testclient import TestClient

priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
pub = priv.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
pub_numbers = priv.public_key().public_numbers()

def _b64(n, l=32):
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

jwks = {"keys": [{
    "kty": "RSA", "alg": "RS256", "use": "sig", "kid": "test-key",
    "n": _b64(pub_numbers.n), "e": _b64(pub_numbers.e),
}]}
import auth
auth.inject_jwks_for_test(os.environ["CLERK_JWKS_URL"], jwks)

def token(org_id, user_id):
    payload = {"sub": user_id, "exp": __import__("time").time() + 600, "o": {"id": org_id},
              "iss": os.environ["CLERK_ISSUER"]}
    return pyjwt.encode(payload, priv, algorithm="RS256", headers={"kid": "test-key"})

import app as app_module
client = TestClient(app_module.app)

org_a, org_b = f"org_{uuid.uuid4().hex[:8]}", f"org_{uuid.uuid4().hex[:8]}"
files = [("authz.txt", b"Workspace authz probe content.")]

r = client.post("/api/brains/v2",
                data={"name": f"authz_{uuid.uuid4().hex[:6]}", "idempotency_key": f"az-{uuid.uuid4()}"},
                files=[("files", files[0])],
                headers={"Authorization": f"Bearer {token(org_a, 'userA')}"})
assert r.status_code == 202, f"create failed: {r.status_code} {r.text[:200]}"
job_id = r.json()["job_id"]
print("  org A created job:", job_id[:8])

r = client.get(f"/api/jobs/{job_id}", headers={"Authorization": f"Bearer {token(org_a, 'userA')}"})
assert r.status_code == 200, f"ALLOW direction failed: {r.status_code}"
print("  ALLOW: org A reads own job: PASS")

r = client.get(f"/api/jobs/{job_id}", headers={"Authorization": f"Bearer {token(org_b, 'userB')}"})
assert r.status_code == 403, f"DENY direction failed: {r.status_code} {r.text[:120]}"
assert "another workspace" in r.text
print("  DENY: org B blocked from A's job: PASS")

r = client.get("/api/jobs/does-not-exist", headers={"Authorization": f"Bearer {token(org_b, 'userB')}"})
assert r.status_code == 404
print("  unknown job -> 404 contract: PASS")

# cleanup
with psycopg.connect(URL, row_factory=psycopg.rows.dict_row) as conn, conn.cursor() as cur:
    cur.execute("""delete from brain_job_staging st using brain_jobs j
                   where st.job_id=j.id and j.id=%s""", (job_id,))
    cur.execute("delete from brain_job_files where job_id=%s", (job_id,))
    cur.execute("delete from brain_job_events where job_id=%s", (job_id,))
    cur.execute("select brain_id, generation_id from brain_jobs where id=%s", (job_id,))
    row = cur.fetchone()
    cur.execute("delete from brain_jobs where id=%s", (job_id,))
    if row:
        cur.execute("update brains set active_generation_id=null where id=%s", (row["brain_id"],))
        cur.execute("delete from brain_generations where id=%s", (row["generation_id"],))
        cur.execute("delete from brains where id=%s", (row["brain_id"],))
        cur.execute("delete from workspaces where clerk_org_id in (%s,%s)", (org_a, org_b))
    conn.commit()
print("V2 WORKSPACE AUTHZ: PASS (allow + deny + 404 contract)")
