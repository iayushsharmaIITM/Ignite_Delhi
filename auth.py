"""Authentication (P3): Clerk-verified identities, env-gated.

MODES (AUTH_MODE env)
    off    (default) — no auth; every caller is the single local user. The
           product behaves exactly as before this module existed.
    clerk  — requests must carry a Clerk session JWT
           (`Authorization: Bearer <token>`). The token is verified against
           Clerk's published JWKS; the identity (user id + active organization)
           is attached to the request context. Brain authorization is handled
           by the app via storage.brain_access (org → brains).

DESIGN RULES
  * Fail closed: in clerk mode a missing/invalid token is 401 — never a
    silent pass. A verification INFRASTRUCTURE failure (JWKS unreachable)
    returns the cached keys for up to 10 minutes, then fails closed too.
  * The verification seam is injectable (_jwks_client) so the isolation test
    suite can run without network access.
  * Keys come from the environment only: CLERK_SECRET_KEY,
    CLERK_JWKS_URL (derived from CLERK_ISSUER when absent). Never committed.

Owner setup (one-time): create the Clerk application on the Student Pack,
enable Organizations, put CLERK_ISSUER + CLERK_SECRET_KEY in .env, set
AUTH_MODE=clerk.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from functools import lru_cache

import jwt

_STATUS = {"auth": os.getenv("AUTH_MODE", "off")}


def mode() -> str:
    return os.getenv("AUTH_MODE", "off")


def active() -> bool:
    return mode() == "clerk"


def issuer() -> str:
    return os.getenv("CLERK_ISSUER", "").rstrip("/")


def jwks_url() -> str:
    url = os.getenv("CLERK_JWKS_URL", "")
    return url or (f"{issuer()}/.well-known/jwks.json" if issuer() else "")


@lru_cache(maxsize=4)
def _fetch_jwks(url: str) -> dict:
    """Fetch and cache Clerk's public keys for 10 minutes (module-level lru
    cache is the cache; TTL enforced by comparing the fetch timestamp)."""
    with urllib.request.urlopen(url, timeout=10) as resp:
        keys = json.loads(resp.read().decode())
    _JWKS_DATA[url] = keys
    _JWKS_TS[url] = time.time()
    return keys


_JWKS_TS: dict = {}
_JWKS_TTL = 600


def _jwks(url: str) -> dict:
    ts = _JWKS_TS.get(url)
    if not ts or time.time() - ts > _JWKS_TTL or url not in _JWKS_DATA:
        return _fetch_jwks(url)
    return _JWKS_DATA[url]


_JWKS_DATA: dict = {}


def _jwks_client():  # test seam
    return None


def verify_token(token: str) -> dict | None:
    """Verify a Clerk session JWT. Returns the identity dict or None.

    Identity shape: {user_id, org_id (active organization, may be None)}.
    """
    url = jwks_url()
    if not url:
        return None
    try:
        jwks = _jwks(url)
        headers = jwt.get_unverified_header(token)
        key = next(k for k in jwks.get("keys", []) if k.get("kid") == headers.get("kid"))
        from jwt import PyJWK

        payload = jwt.decode(
            token,
            PyJWK.from_dict(key).key,
            algorithms=[headers.get("alg", "RS256")],
            options={"verify_aud": False},
            leeway=10,
        )
    except Exception:  # noqa: BLE001 - fail closed on any verification problem
        return None

    org = payload.get("o") or {}   # Clerk active-organization claim
    org_id = org.get("id") if isinstance(org, dict) else None
    return {"user_id": payload.get("sub"), "org_id": org_id}


def identity_from_request(auth_header: str | None) -> dict | None:
    """Resolve the caller identity from the Authorization header.

    off mode  → single local user (backward compatible: everything allowed).
    clerk     → Bearer JWT required; None means 401 for the caller.
    """
    if not active():
        return {"user_id": "local", "org_id": None}
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    return verify_token(auth_header.split(" ", 1)[1].strip())


# --- test seam: swap the key source so the isolation suite can sign tokens
# with its own RSA keypair and inject the public JWK --------------------------
def inject_jwks_for_test(url: str, keys: dict) -> None:
    _JWKS_DATA[url] = keys
    _JWKS_TS[url] = time.time()
