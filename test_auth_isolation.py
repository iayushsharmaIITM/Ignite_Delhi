"""P3 isolation suite: two Clerk identities, cross-brain access denied.

Runs WITHOUT network: the Clerk JWT verifier's JWKS source is injected with a
test RSA keypair, tokens are signed locally. Exercises auth.py + the app's
brain-authorization rule with AUTH_MODE=clerk.

    python3 test_auth_isolation.py
"""

from __future__ import annotations

import os
import time

import jwt
import pytest

os.environ["AUTH_MODE"] = "clerk"

import auth  # noqa: E402
import storage  # noqa: E402

# Fail-closed authz (SEC-2) made prod-DB testing dangerous: seed rows now
# change access decisions, so this suite gets its OWN database. Created once,
# scrubbed per test module run — production chats are never touched.
_TEST_DB = "kestrel_test_auth"


def _use_test_db() -> None:
    import psycopg
    admin = storage.DATABASE_URL.rsplit("/", 1)[0] + "/kestrel"
    with psycopg.connect(admin, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (_TEST_DB,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{_TEST_DB}"')
    storage.DATABASE_URL = admin.rsplit("/", 1)[0] + f"/{_TEST_DB}"
    assert storage.init(), "test database init failed"
    with psycopg.connect(storage.DATABASE_URL, autocommit=True) as conn:
        for tbl in ("turns", "chats", "brain_access", "llm_calls"):
            conn.execute(f"TRUNCATE {tbl} CASCADE")


_use_test_db()

# --- test keypair ------------------------------------------------------------
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUB = _KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
_KID = "test-kid"

TEST_URL = "https://clerk.test/.well-known/jwks.json"


@pytest.fixture(scope="module", autouse=True)
def setup():
    from jwt import PyJWK  # noqa: F401  (verifies the import path works)
    import base64

    numbers = _KEY.public_key().public_numbers()
    def b64u(i):
        b = i.to_bytes((i.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    jwks = {"keys": [{"kid": _KID, "kty": "RSA", "alg": "RS256", "use": "sig",
                      "n": b64u(numbers.n), "e": b64u(numbers.e)}]}
    os.environ["CLERK_JWKS_URL"] = TEST_URL
    auth._JWKS_TS.clear()
    auth._JWKS_DATA.clear()
    auth.inject_jwks_for_test(TEST_URL, jwks)
    yield


def token(user: str, org: str | None) -> str:
    # Realistic Clerk shape: RS256 + kid header and an expiry (verify
    # requires exp — an unexpiring token is a forever-token).
    return jwt.encode({"sub": user, "o": {"id": org} if org else None,
                       "iat": int(time.time()),
                       "exp": int(time.time()) + 600},
                      _KEY, algorithm="RS256", headers={"kid": _KID})


def test_verify_roundtrip():
    identity = auth.identity_from_request("Bearer " + token("user_A", "org_A"))
    assert identity == {"user_id": "user_A", "org_id": "org_A"}


def test_verify_roundtrip_within_ttl():
    """Second verification inside the 10-minute cache window must also pass.

    Regression: _fetch_jwks recorded the fetch timestamp but never stored the
    keys, so the first call succeeded (fresh fetch) and every later call inside
    the TTL hit a KeyError in _jwks and failed closed — production auth broke
    on the second request after each fetch.
    """
    tok = "Bearer " + token("user_A", "org_A")
    first = auth.identity_from_request(tok)
    second = auth.identity_from_request(tok)   # cache-warm path
    assert first == second == {"user_id": "user_A", "org_id": "org_A"}
    # and the cached entry must really be the key material, not a miss
    assert TEST_URL in auth._JWKS_DATA
    assert auth._JWKS_DATA[TEST_URL]["keys"][0]["kid"] == _KID


def test_garbage_token_fails_closed():
    assert auth.identity_from_request("Bearer not-a-jwt") is None
    assert auth.identity_from_request(None) is None


def test_brain_access_rules():
    storage.init()
    storage.register_brain("acme_isolated", "org_A", "user_A")
    storage.register_brain("company_brain", None, None, shared=True)

    from fastapi import HTTPException

    class FakeRequest:
        state = type("S", (), {})()

    req = FakeRequest()
    req.state.identity = {"user_id": "user_A", "org_id": "org_A"}
    # owner may read their brain; shared readable; other org denied
    from app import brain_allowed
    brain_allowed(req, "acme_isolated")
    brain_allowed(req, "company_brain")
    req.state.identity = {"user_id": "user_B", "org_id": "org_B"}
    with pytest.raises(HTTPException) as exc:
        brain_allowed(req, "acme_isolated")
    assert exc.value.status_code == 403


def test_chat_isolation():
    storage.init()
    # SEC-5: ownership is server-stamped (org=...), never taken from the
    # record — a client-supplied org_id is ignored by contract.
    storage.upsert_chat({"id": "iso-a", "brain": "acme_isolated",
                         "org_id": "org_EVIL",
                         "title": "A chat",
                         "turns": [{"role": "user", "text": "q"}]},
                        org="org_A", brain="acme_isolated")
    chats = storage.list_chats("acme_isolated", org="org_B")
    assert all(c["id"] != "iso-a" for c in chats)
    chats = storage.list_chats("acme_isolated", org="org_A")
    assert any(c["id"] == "iso-a" for c in chats)
    storage.delete_chat("iso-a")
