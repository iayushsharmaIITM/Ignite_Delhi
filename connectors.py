"""P6 connectors, part 1: OAuth connect flow + encrypted credential vault.

Two halves that compose into working integrations:

  CONNECT:  GET /api/connectors/oauth/{google,slack}/start
            → 302 to the provider (minimal scopes, offline access)
            GET /api/connectors/oauth/{provider}/callback?code&state
            → exchange code for tokens → Fernet-encrypted row in Postgres.
            The browser never sees a token; only /?connected=<provider>.

  USE:      import/send paths resolve credentials per identity from the
            vault first, env tokens second (dev/legacy behavior preserved).
            Expired Google tokens refresh inline; revoked/rotated tokens flip
            the row to needs_reconnect instead of erroring mid-sync — the #1
            connector UX failure mode industry-wide.

Security contract:
  * Fernet key comes ONLY from CONNECTOR_VAULT_KEY env (generate with
    `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
    No key → vault functions raise at write time; reads behave as unconnected.
  * No token (or key) is ever logged, returned to the client, or committed.
    .env/.env.oss are gitignored; verify with `git status` before committing.
  * OAuth `state` is a server-side random binding (identity + provider +
    expiry), not a signed blob the client could mint.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import time
import urllib.parse

import requests

# --------------------------------------------------------------------------
# provider registry (OAuth endpoints + minimal scopes — never more)
# --------------------------------------------------------------------------

PROVIDERS = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        # Read-only mail + drive. Restricted scopes: production use needs a
        # CASA assessment; pilot runs in Google testing-mode (100-user cap)
        # or self-hosters bring their own OAuth client (Onyx pattern).
        "scopes": [
            "openid", "email",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
        "client_id_env": "GOOGLE_OAUTH_CLIENT_ID",
        "client_secret_env": "GOOGLE_OAUTH_CLIENT_SECRET",
    },
    "slack": {
        "auth_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        # Read history + names. chat:write deliberately absent: this flow
        # grants READ; sending keeps using the separate webhook path.
        "scopes": ["channels:history", "channels:read",
                   "groups:history", "groups:read", "users:read"],
        "client_id_env": "SLACK_CLIENT_ID",
        "client_secret_env": "SLACK_CLIENT_SECRET",
    },
}

STATE_TTL = 600
_states: dict[str, dict] = {}   # state token -> {identity, provider, exp}


# --------------------------------------------------------------------------
# vault crypto (Fernet, key from env only)
# --------------------------------------------------------------------------

def _fernet():
    key = (os.getenv("CONNECTOR_VAULT_KEY") or "").strip()
    if not key:
        raise RuntimeError("CONNECTOR_VAULT_KEY is not set — vault writes refused.")
    from cryptography.fernet import Fernet
    return Fernet(key.encode() if isinstance(key, str) else key)


def vault_configured() -> bool:
    return bool((os.getenv("CONNECTOR_VAULT_KEY") or "").strip())


def encrypt_blob(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return _fernet().encrypt(raw).decode()


def decrypt_blob(token: str) -> dict:
    return json.loads(_fernet().decrypt(token.encode()))


# --------------------------------------------------------------------------
# vault rows (Postgres; same never-raise discipline as storage.py for reads)
# --------------------------------------------------------------------------

def init_vault() -> bool:
    """CREATE TABLE IF NOT EXISTS connector_credentials. True when usable."""
    if not vault_configured():
        return False
    try:
        import psycopg
        from storage import DATABASE_URL
        with psycopg.connect(DATABASE_URL, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS connector_credentials (
                     provider text NOT NULL,
                     owner_key text NOT NULL,
                     blob text NOT NULL,
                     scopes text NOT NULL DEFAULT '',
                     expires_at timestamptz,
                     status text NOT NULL DEFAULT 'connected',
                     updated timestamptz NOT NULL DEFAULT now(),
                     PRIMARY KEY (provider, owner_key)
                   )""")
        return True
    except Exception:
        return False


def _owner_key(identity: dict | None) -> str:
    ident = identity or {}
    return (ident.get("org_id") or "") + "|" + (ident.get("user_id") or "")


def put_credential(provider: str, identity: dict | None, tokens: dict,
                   scopes: str = "") -> None:
    """Encrypt + upsert. Raises if the vault key is missing (fail LOUD —
    silently dropping an OAuth grant would read as 'connected, then broken')."""
    blob = encrypt_blob({
        "access_token": tokens.get("access_token", ""),
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at": tokens.get("expires_at", 0),
        "extra": {k: v for k, v in tokens.items()
                  if k not in ("access_token", "refresh_token", "expires_at")},
    })
    import psycopg
    from storage import DATABASE_URL
    # 0 / None => "never expires" (Slack bot tokens, Google without expires_in).
    # to_timestamp() is typed double precision explicitly; without the cast
    # Postgres cannot infer the type of a NULL parameter and the write dies.
    exp = tokens.get("expires_at") or 0
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO connector_credentials
                 (provider, owner_key, blob, scopes, expires_at, status, updated)
               VALUES (%s, %s, %s, %s,
                       CASE WHEN %s > 0
                            THEN to_timestamp(%s::double precision)
                            ELSE NULL END,
                       'connected', now())
               ON CONFLICT (provider, owner_key) DO UPDATE SET
                 blob = EXCLUDED.blob, scopes = EXCLUDED.scopes,
                 expires_at = EXCLUDED.expires_at,
                 status = 'connected', updated = now()""",
            (provider, _owner_key(identity), blob, scopes, exp, exp))


def get_credential(provider: str, identity: dict | None) -> dict | None:
    """Decrypted tokens, or None (no row / vault down / corrupt row — the
    caller falls back to env tokens, then to 'not configured')."""
    try:
        import psycopg
        from storage import DATABASE_URL
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT blob, status, scopes FROM connector_credentials "
                "WHERE provider = %s AND owner_key = %s",
                (provider, _owner_key(identity)))
            row = cur.fetchone()
        if not row:
            return None
        blob, status, scopes = row[0], row[1], row[2]
        data = decrypt_blob(blob)
        data["_status"] = status
        data["scopes"] = scopes
        return data
    except Exception:
        return None


def mark_needs_reconnect(provider: str, identity: dict | None) -> None:
    try:
        import psycopg
        from storage import DATABASE_URL
        with psycopg.connect(DATABASE_URL, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE connector_credentials SET status = 'needs_reconnect', "
                "updated = now() WHERE provider = %s AND owner_key = %s",
                (provider, _owner_key(identity)))
    except Exception:
        pass


def delete_credential(provider: str, identity: dict | None) -> bool:
    try:
        import psycopg
        from storage import DATABASE_URL
        with psycopg.connect(DATABASE_URL, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM connector_credentials "
                "WHERE provider = %s AND owner_key = %s",
                (provider, _owner_key(identity)))
            return cur.rowcount > 0
    except Exception:
        return False


def connection_state(provider: str, identity: dict | None,
                     env_token: str | None = None) -> str:
    """connected | needs_reconnect | unconfigured — what the UI pill shows.

    A vault row always wins. `env_token` (the legacy single-tenant dev path)
    counts as connected only when it is actually non-empty, so an instance
    with no credentials never advertises a transport it cannot serve.
    """
    cred = get_credential(provider, identity)
    if cred and cred.get("_status") == "connected" and cred.get("access_token"):
        return "connected"
    if cred:
        return "needs_reconnect"
    return "connected" if (env_token or "").strip() else "unconfigured"


# --------------------------------------------------------------------------
# OAuth: state binding, authorize URL, code exchange, refresh
# --------------------------------------------------------------------------

def redirect_uri(provider: str) -> str:
    base = (os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")
    return f"{base}/api/connectors/oauth/{provider}/callback"


def provider_configured(provider: str) -> bool:
    cfg = PROVIDERS.get(provider)
    if not cfg:
        return False
    return bool(os.getenv(cfg["client_id_env"], "").strip()
                and os.getenv(cfg["client_secret_env"], "").strip())


def mint_state(identity: dict | None, provider: str) -> str:
    token = secrets.token_urlsafe(24)
    _states[token] = {"identity": identity or {},
                      "provider": provider, "exp": time.time() + STATE_TTL}
    return token


def pop_state(token: str, provider: str) -> dict | None:
    rec = _states.pop(token, None)
    if not rec or rec.get("provider") != provider or rec["exp"] < time.time():
        return None
    return rec["identity"]


def authorize_url(provider: str, identity: dict | None) -> str:
    cfg = PROVIDERS[provider]
    params = {
        "client_id": os.getenv(cfg["client_id_env"], "").strip(),
        "redirect_uri": redirect_uri(provider),
        "response_type": "code",
        "scope": " ".join(cfg["scopes"]) if provider == "google"
                 else ",".join(cfg["scopes"]),
        "state": mint_state(identity, provider),
    }
    if provider == "google":
        # Offline refresh tokens + no surprise re-consent screens.
        params.update(access_type="offline", prompt="consent",
                      include_granted_scopes="false")
    return cfg["auth_url"] + "?" + urllib.parse.urlencode(params)


def exchange_code(provider: str, code: str) -> tuple[dict, str]:
    """Returns (tokens, granted_scopes). Raises RuntimeError on refusal."""
    cfg = PROVIDERS[provider]
    try:
        r = requests.post(cfg["token_url"], data={
            "client_id": os.getenv(cfg["client_id_env"], "").strip(),
            "client_secret": os.getenv(cfg["client_secret_env"], "").strip(),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri(provider),
        }, timeout=30)
        data = r.json()
    except Exception as exc:
        raise RuntimeError(f"token exchange failed: {exc}") from exc
    if provider == "slack":
        if not data.get("ok"):
            raise RuntimeError("Slack refused the code: "
                               + str(data.get("error", "?"))[:120])
        return ({
            "access_token": data.get("access_token", ""),
            # Bot tokens do not expire; rotation surfaces as invalid_auth.
            "refresh_token": "",
            "expires_at": 0,
            "team": (data.get("team") or {}).get("name", ""),
        }, ",".join((data.get("scope") or "").split(",")))
    # google
    if "access_token" not in data:
        raise RuntimeError("Google refused the code: "
                           + str(data.get("error_description")
                                 or data.get("error", "?"))[:160])
    return ({
        "access_token": data.get("access_token", ""),
        "refresh_token": data.get("refresh_token", ""),
        "expires_at": (int(time.time()) + int(data.get("expires_in") or 3600)
                       if data.get("expires_in") else 0),
    }, data.get("scope", ""))


def google_access_token(identity: dict | None,
                        stored: dict | None = None) -> str | None:
    """Valid access token: stored one if fresh, else silent refresh.
    Returns None (caller falls back / reports unconfigured) and flips the
    row to needs_reconnect when the grant is dead (revoked/rotated)."""
    cred = stored if stored is not None else get_credential("google", identity)
    if not cred or not cred.get("access_token"):
        return None
    if cred.get("_status") != "connected":
        return None
    exp = cred.get("expires_at") or 0
    if exp and exp - time.time() > 120:
        return cred["access_token"]
    refresh = cred.get("refresh_token") or ""
    if not refresh:
        return cred["access_token"]  # no expiry tracked: use until refused
    cfg = PROVIDERS["google"]
    try:
        r = requests.post(cfg["token_url"], data={
            "client_id": os.getenv(cfg["client_id_env"], "").strip(),
            "client_secret": os.getenv(cfg["client_secret_env"], "").strip(),
            "grant_type": "refresh_token",
            "refresh_token": refresh,
        }, timeout=30)
        data = r.json()
    except Exception:
        # Transport blip (DNS, timeout, 5xx) is NOT a dead grant. Leave the row
        # 'connected' so a flaky network never forces a re-consent, and hand
        # back the stale token — the Gmail call will 401 if it truly died.
        return cred["access_token"]
    if "access_token" not in data:
        # Google answering means the grant itself is gone (revoked, or the
        # refresh token was rotated away). That is the only case that should
        # downgrade the row to needs_reconnect.
        if str(data.get("error", "")) in (
                "invalid_grant", "invalid_token", "unauthorized_client",
                "invalid_client", "access_denied"):
            mark_needs_reconnect("google", identity)
        return None
    fresh = dict(cred)
    fresh["access_token"] = data["access_token"]
    fresh["expires_at"] = int(time.time()) + int(data.get("expires_in") or 3600)
    if data.get("refresh_token"):
        fresh["refresh_token"] = data["refresh_token"]
    try:
        put_credential("google", identity, fresh,
                       scopes=" ".join(PROVIDERS["google"]["scopes"]))
    except Exception:
        pass
    return fresh["access_token"]


def slack_token(identity: dict | None) -> str | None:
    """Vault bot token, else legacy env token. Rotation surfaces as
    invalid_auth at call time — callers must map that to needs_reconnect."""
    cred = get_credential("slack", identity)
    if cred and cred.get("_status") == "connected" and cred.get("access_token"):
        return cred["access_token"]
    return os.getenv("SLACK_BOT_TOKEN", "").strip() or None
