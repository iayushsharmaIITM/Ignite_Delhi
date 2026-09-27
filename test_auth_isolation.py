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
    return jwt.encode({"sub": user, "o": {"id": org} if org else None,
                       "iat": int(time.time())},
                      _KEY, algorithm="RS256", headers={"kid": _KID})


def test_verify_roundtrip():
    identity = auth.identity_from_request("Bearer " + token("user_A", "org_A"))
    assert identity == {"user_id": "user_A", "org_id": "org_A"}


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
    storage.upsert_chat({"id": "iso-a", "brain": "acme_isolated", "org_id": "org_A",
                         "title": "A chat",
                         "turns": [{"role": "user", "text": "q"}]})
    chats = storage.list_chats("acme_isolated", org="org_B")
    assert all(c["id"] != "iso-a" for c in chats)
    chats = storage.list_chats("acme_isolated", org="org_A")
    assert any(c["id"] == "iso-a" for c in chats)
    storage.delete_chat("iso-a")
