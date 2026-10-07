"""Authentication (P3): Clerk-verified identities, env-gated.

MODES (AUTH_MODE env)
    clerk  (DEFAULT) — see below. Absence of the variable means clerk, not off:
           a deploy that forgets to decide must not end up public.
    off    (explicit only) — no auth; every caller is the single local user. This
           is the verification seam: verify.sh, both CI jobs and restore_lab.sh
           name it deliberately. It is never the fallback.
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
import urllib.parse
import urllib.request

import jwt

_ALLOWED_MODES = ("clerk", "off")


def mode() -> str:
    """`clerk` unless `off` is asked for EXPLICITLY.

    The default used to be "off", which meant a deploy that forgot to set AUTH_MODE
    served every tenant's chats, brains and graph to anyone who could reach the port —
    the failure this module exists to prevent, arriving by omission rather than by
    attack. Sign-in is now the product's only entry, so the absence of a decision
    means auth is ON.

    `off` stays as a deliberate, explicit seam: verify.sh, both CI jobs and
    ops/restore_lab.sh each set it by name, and the battery cannot run without it.

    An unrecognised value raises instead of falling through. `AUTH_MODE=clerrk` used to
    mean "no authentication", which is the wrong thing for a typo to mean.
    """
    raw = (os.getenv("AUTH_MODE") or "").strip().lower()
    if not raw:
        return "clerk"
    if raw not in _ALLOWED_MODES:
        raise RuntimeError(
            f"AUTH_MODE={raw!r} is not one of {list(_ALLOWED_MODES)}. Refusing to "
            "start rather than silently disabling authentication.")
    return raw


def active() -> bool:
    return mode() == "clerk"


def issuer() -> str:
    return os.getenv("CLERK_ISSUER", "").rstrip("/")


def jwks_url() -> str:
    url = os.getenv("CLERK_JWKS_URL", "")
    return url or (f"{issuer()}/.well-known/jwks.json" if issuer() else "")


def _fetch_jwks(url: str) -> dict:
    """Fetch Clerk's public keys. No cache here — `_jwks` below owns the TTL.

    (An lru_cache used to sit on this function, which silently disabled the
    TTL: cache hits never re-stamped the timestamp, so keys were fetched once
    per process and a Clerk rotation broke auth until restart.)
    """
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode())


_JWKS_TS: dict = {}
_JWKS_TTL = 600


_JWKS_GRACE = 600       # serve stale keys this long past the TTL, then fail closed
_JWKS_RETRY = 60        # do not re-hit an unreachable JWKS once per request


def _jwks(url: str) -> dict:
    """Keys for this URL, honouring the module's own fail-closed contract.

    The contract at the top of this file says an INFRASTRUCTURE failure serves the
    cached keys for up to ten minutes and then fails closed. The first version did
    neither half correctly past the TTL: it re-fetched with no try/except, so a Clerk
    outage (a) threw away perfectly good cached keys instead of serving them in a
    grace window, (b) never re-stamped the timestamp, so EVERY request paid its own
    blocking 10-second fetch on the event loop — `require_tenant` is called from
    `async def` handlers, so the whole tier stalls — and (c) 401'd every signed-in
    user at once, including with tokens that validated minutes earlier.
    """
    now = time.time()
    ts = _JWKS_TS.get(url)
    fresh = ts is not None and now - ts <= _JWKS_TTL
    if not fresh and url not in _JWKS_DATA:
        _JWKS_DATA[url] = _fetch_jwks(url)
        _JWKS_TS[url] = now
        return _JWKS_DATA[url]
    if fresh:
        return _JWKS_DATA[url]
    # Past the TTL: try to refresh, but never let a failed refresh discard the keys
    # or turn into a per-request network stall.
    last_try = _JWKS_RETRY_TS.get(url, 0)
    if now - last_try < _JWKS_RETRY:
        age = now - (ts or 0)
        if age <= _JWKS_TTL + _JWKS_GRACE:
            return _JWKS_DATA[url]        # stale-but-accepted window, per the contract
        raise RuntimeError("Clerk JWKS unreachable and cached keys are too old")
    _JWKS_RETRY_TS[url] = now
    try:
        keys = _fetch_jwks(url)
    except Exception as exc:  # noqa: BLE001 - decide below, never discard silently
        age = now - (ts or 0)
        if age <= _JWKS_TTL + _JWKS_GRACE:
            return _JWKS_DATA[url]
        raise RuntimeError(f"Clerk JWKS unreachable and cached keys are too old: "
                           f"{str(exc)[:120]}") from exc
    _JWKS_DATA[url] = keys
    _JWKS_TS[url] = now
    return keys


_JWKS_DATA: dict = {}
_JWKS_RETRY_TS: dict = {}   # url -> last refresh attempt, for the backoff above


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

        # S4: pin the issuer when configured — any RS256 token from the JWKS
        # key is not automatically OUR session (cross-template replay).
        decode_kw: dict = {
            "algorithms": ["RS256"],
            "options": {"verify_aud": False, "require": ["exp"]},
            "leeway": 10,
        }
        if issuer():
            decode_kw["issuer"] = issuer()
        payload = jwt.decode(
            token,
            PyJWK.from_dict(key).key,
            **decode_kw,  # LOW-7: never take the algorithm from the token header, and
            # require expiry — an unexpiring token is a forever-token.
        )
    except Exception:  # noqa: BLE001 - fail closed on any verification problem
        return None

    # S4: Clerk's org claim shape varies (active-org "o" object, occasionally
    # a top-level org_id string or orgs array). Accept the known shapes;
    # anything else is org-less, never someone else's org.
    org = payload.get("o") or {}
    org_id = org.get("id") if isinstance(org, dict) else None
    if not org_id and isinstance(payload.get("org_id"), str):
        org_id = payload["org_id"]
    if not org_id and isinstance(payload.get("orgs"), list) \
            and len(payload["orgs"]) == 1 and isinstance(payload["orgs"][0], dict):
        org_id = payload["orgs"][0].get("id")
    return {"user_id": payload.get("sub"), "org_id": org_id}


def identity_from_request(auth_header: str | None = None,
                          cookie: str | None = None,
                          query_token: str | None = None) -> dict | None:
    """Resolve the caller identity from the Authorization header, session cookie,
    or query token parameter.

    off mode  → single local user (backward compatible: everything allowed).
    clerk     → Bearer JWT required; None means 401 for the caller.
    """
    if not active():
        return {"user_id": "local", "org_id": None}
    candidates: list[str] = []
    if auth_header and auth_header.lower().startswith("bearer "):
        candidates.append(auth_header.split(" ", 1)[1].strip())
    if query_token:
        candidates.append(urllib.parse.unquote(query_token.strip()).strip('"'))
    if cookie:
        candidates.append(urllib.parse.unquote(cookie.strip()).strip('"'))

    for token in candidates:
        if not token:
            continue
        ident = verify_token(token)
        if ident is not None:
            return ident

    return None


# --- test seam: swap the key source so the isolation suite can sign tokens
# with its own RSA keypair and inject the public JWK --------------------------
def inject_jwks_for_test(url: str, keys: dict) -> None:
    _JWKS_DATA[url] = keys
    _JWKS_TS[url] = time.time()
