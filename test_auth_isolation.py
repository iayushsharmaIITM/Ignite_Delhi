"""P3 isolation suite: two Clerk identities, cross-brain access denied.

Runs WITHOUT network: the Clerk JWT verifier's JWKS source is injected with a
test RSA keypair, tokens are signed locally. Exercises auth.py + the app's
brain-authorization rule with AUTH_MODE=clerk.

    DATABASE_URL=<lab 5434> python3 test_auth_isolation.py
    DATABASE_URL=<lab 5434> python3 -m pytest test_auth_isolation.py -q

Both routes run all five checks. They used to differ: the file had no runner, so
`python3 test_auth_isolation.py` imported the module (creating a database),
defined five tests, ran none of them, and exited 0 — a green that measured
nothing. pytest is still required to import this file (fixtures and `raises`), so
it needs `pip install pytest`, which requirements-dev.txt does not carry.
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
    # The same rule the battery applies to every suite that writes: with no
    # DATABASE_URL this module falls through to .env — the LIVE demo database —
    # and this function CREATES a database there and TRUNCATES tables in it. The
    # isolation the suite needs is real; the server it runs on was not guarded.
    url = storage.DATABASE_URL
    if "5434" not in url and os.environ.get("KESTREL_ALLOW_LIVE_DB", "0") != "1":
        raise SystemExit(
            "REFUSING: this suite creates and truncates a database on the server "
            f"named by DATABASE_URL ({url.split('@')[-1] if '@' in url else url}). "
            "Point it at the lab (port 5434), or insist with KESTREL_ALLOW_LIVE_DB=1.")
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


def _inject_jwks() -> None:
    """Serve the verifier a local keypair. Shared by pytest's fixture and the
    standalone runner below, so neither route can drift from the other."""
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


@pytest.fixture(scope="module", autouse=True)
def setup():
    _inject_jwks()
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
    # CH-2 made deletions durable, so a FIXED fixture id would collide with its
    # own tombstone on a second run of this file. Each run uses a fresh id, and
    # the tombstone rule is asserted rather than stumbled into.
    cid = f"iso-a-{int(time.time() * 1000)}"
    record = {"id": cid, "brain": "acme_isolated",
              "org_id": "org_EVIL",
              "title": "A chat",
              "turns": [{"role": "user", "text": "q"}]}
    # SEC-5: ownership is server-stamped (org=...), never taken from the
    # record — a client-supplied org_id is ignored by contract.
    storage.upsert_chat(record, org="org_A", brain="acme_isolated")
    chats = storage.list_chats("acme_isolated", org="org_B")
    assert all(c["id"] != cid for c in chats)
    chats = storage.list_chats("acme_isolated", org="org_A")
    assert any(c["id"] == cid for c in chats)
    assert storage.delete_chat(cid) is True
    with pytest.raises(storage.ResurrectError):
        storage.upsert_chat(record, org="org_A", brain="acme_isolated")


def test_default_mode_is_clerk():
    """Sign-in is the product's only entry, so forgetting to decide must not mean open.

    Run in a SUBPROCESS because this module pins AUTH_MODE=clerk at import, and the
    thing under test is precisely what a process with no AUTH_MODE at all does.
    """
    import subprocess
    import sys

    def probe(value):
        env = {k: v for k, v in os.environ.items() if k != "AUTH_MODE"}
        if value is not None:
            env["AUTH_MODE"] = value
        out = subprocess.run([sys.executable, "-c", "import auth; print(auth.mode())"],
                             capture_output=True, text=True, env=env, cwd=os.getcwd())
        return out

    unset = probe(None)
    assert unset.returncode == 0, unset.stderr[-300:]
    assert unset.stdout.strip() == "clerk", \
        f"an unset AUTH_MODE resolved to {unset.stdout.strip()!r}, not 'clerk'"

    explicit_off = probe("off")
    assert explicit_off.stdout.strip() == "off", \
        "the verification seam must still be selectable explicitly"

    # A typo must not become "no authentication".
    garbage = probe("clerrk")
    assert garbage.returncode != 0, "AUTH_MODE=clerrk was accepted"
    assert "not one of" in garbage.stderr, garbage.stderr[-300:]


def _run_all() -> int:
    """Standalone entrypoint, so `python3 test_auth_isolation.py` runs the checks
    instead of importing them. Reports in the format verify.sh's tally counts."""
    _inject_jwks()
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = []
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001 - report, never swallow
            failed.append(t.__name__)
            print(f"  FAIL  {t.__name__}  {type(exc).__name__}: {str(exc)[:120]}")
    print(f"\n{len(tests) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
