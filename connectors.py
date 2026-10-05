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
import logging
import os
import secrets
import time
import urllib.parse

import requests

log = logging.getLogger("kestrel.connectors")

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
# Upper bound on outstanding (unconsumed, unexpired) OAuth states. mint_state used to
# only ever add, so abandoned connect clicks accumulated until the process restarted.
STATE_CAP = 2000
_states: dict[str, dict] = {}   # state token -> {identity, provider, exp}

# A rotated refresh token we could not persist. The request still succeeds on its
# access token, so this is not an error the caller can act on — but it is an error the
# operator must be able to see, because the stored grant silently goes stale.
_rotation_losses: dict = {"count": 0, "owner": "", "at": 0.0}

# The five OAuth codes that mean THIS grant is dead. Anything else the provider says
# is either our application's problem or provider weather — see refresh_failure().
REVOKED_GRANT_ERRORS = frozenset({"invalid_grant", "invalid_token", "access_denied"})
APPLICATION_CONFIG_ERRORS = frozenset({"invalid_client", "unauthorized_client"})


def rotation_losses() -> dict:
    """{count, owner, at} — the last rotation whose new refresh token could not be saved."""
    return dict(_rotation_losses)


def _prune_states() -> None:
    """Forget expired OAuth states, then keep the outstanding set inside STATE_CAP."""
    now = time.time()
    for token, rec in list(_states.items()):
        if rec["exp"] < now:
            _states.pop(token, None)
    while len(_states) > STATE_CAP:
        oldest = min(_states, key=lambda t: _states[t]["exp"])
        _states.pop(oldest, None)


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



# ==========================================================================
# P6 Slack for general users: multi-workspace, scope-picker, read/post
# ---------------------------------------------------------------------------
# The single-grant flow above connects ONE Slack workspace with fixed read
# scopes. This layer adds what general users need, modeled on the Notion-style
# "Configure access" dialog:
#
#   * a scope picker (read-only vs read+post, private-channel toggle) — the
#     dialog choice is just a different scope set sent to Slack
#   * one bot token per workspace (bot tokens are workspace-scoped), stored
#     encrypted per (identity, team)
#   * channels list / message read / post-message, with post refused 403
#     unless chat:write was actually granted
#   * disconnect through auth.revoke
#
# Slack error mapping: 429 honors Retry-After; not_in_channel, missing_scope,
# invalid_auth and token_revoked surface as human sentences, never raw codes.
# ==========================================================================

SLACK_SCOPE_SETS = {
    "read":      ["channels:read", "channels:history"],
    "read_post": ["channels:read", "channels:history", "chat:write"],
}
SLACK_PRIVATE_BOT = ["groups:read", "groups:history"]
SLACK_PRIVATE_USER = ["im:history", "mpim:history"]


def slack_scope_set(mode: str, private: bool) -> tuple[list, list]:
    """Dialog choice -> (bot_scopes, user_scopes). DMs need USER tokens —
    bot tokens cannot read IM/MPIM, which is why the toggle requests
    user_scopes when private access is on."""
    bot = list(SLACK_SCOPE_SETS.get(mode if mode in SLACK_SCOPE_SETS else "read"))
    if private:
        bot += [s for s in SLACK_PRIVATE_BOT if s not in bot]
    user = list(SLACK_PRIVATE_USER) if private else []
    return bot, user


def slack_connect_url(identity: dict | None, mode: str, private: bool) -> str:
    """Authorize URL for the chosen access level. state binds identity +
    the requested mode/private so the callback stores what was consented."""
    cfg = PROVIDERS["slack"]
    bot, user = slack_scope_set(mode, private)
    token = mint_state(identity, "slack",
                       extra={"mode": mode, "private": bool(private)})
    params = {
        "client_id": os.getenv(cfg["client_id_env"], "").strip(),
        "redirect_uri": redirect_uri("slack"),
        "response_type": "code",
        "scope": ",".join(bot),
        "state": token,
    }
    if user:
        params["user_scope"] = ",".join(user)
    return cfg["auth_url"] + "?" + urllib.parse.urlencode(params)


def init_slack_workspaces() -> bool:
    """CREATE TABLE IF NOT EXISTS slack_workspaces. True when usable."""
    if not vault_configured():
        return False
    try:
        import psycopg
        from storage import DATABASE_URL
        with psycopg.connect(DATABASE_URL, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS slack_workspaces (
                     owner_key text NOT NULL,
                     team_id text NOT NULL,
                     team_name text NOT NULL DEFAULT '',
                     blob text NOT NULL,
                     scopes text NOT NULL DEFAULT '',
                     mode text NOT NULL DEFAULT 'read',
                     private boolean NOT NULL DEFAULT false,
                     bot_user_id text NOT NULL DEFAULT '',
                     connected timestamptz NOT NULL DEFAULT now(),
                     PRIMARY KEY (owner_key, team_id)
                   )""")
        return True
    except Exception:
        return False


def slack_put_workspace(identity: dict | None, team_id: str, team_name: str,
                        tokens: dict, scopes: str, mode: str, private: bool,
                        bot_user_id: str = "") -> None:
    if not vault_configured():
        raise RuntimeError("CONNECTOR_VAULT_KEY is not set — vault writes refused.")
    blob = encrypt_blob({
        "bot_token": tokens.get("bot_token", ""),
        "user_token": tokens.get("user_token", ""),
        "bot_user_id": bot_user_id,
    })
    import psycopg
    from storage import DATABASE_URL
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO slack_workspaces
                 (owner_key, team_id, team_name, blob, scopes, mode, private,
                  bot_user_id, connected)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
               ON CONFLICT (owner_key, team_id) DO UPDATE SET
                 team_name = EXCLUDED.team_name, blob = EXCLUDED.blob,
                 scopes = EXCLUDED.scopes, mode = EXCLUDED.mode,
                 private = EXCLUDED.private, bot_user_id = EXCLUDED.bot_user_id,
                 connected = now()""",
            (_owner_key(identity), team_id, team_name, blob, scopes,
             mode, bool(private), bot_user_id))


def slack_list_workspaces(identity: dict | None) -> list[dict]:
    """Connected workspaces WITHOUT tokens — the UI list only ever sees
    team info, mode and scopes."""
    try:
        import psycopg
        from storage import DATABASE_URL
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT team_id, team_name, scopes, mode, private, connected
                   FROM slack_workspaces WHERE owner_key = %s
                   ORDER BY connected DESC""",
                (_owner_key(identity),))
            rows = cur.fetchall()
        return [{"team_id": r[0], "team_name": r[1], "scopes": r[2],
                 "mode": r[3], "private": r[4], "connected": str(r[5])}
                for r in rows]
    except Exception:
        return []


def slack_get_workspace(identity: dict | None, team_id: str) -> dict | None:
    """Decrypted workspace tokens + meta, or None."""
    try:
        import psycopg
        from storage import DATABASE_URL
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT team_name, blob, scopes, mode, private
                   FROM slack_workspaces WHERE owner_key = %s AND team_id = %s""",
                (_owner_key(identity), team_id))
            row = cur.fetchone()
        if not row:
            return None
        data = decrypt_blob(row[1])
        return {"team_id": team_id, "team_name": row[0],
                "bot_token": data.get("bot_token", ""),
                "user_token": data.get("user_token", ""),
                "bot_user_id": data.get("bot_user_id", ""),
                "scopes": row[2], "mode": row[3], "private": row[4]}
    except Exception:
        return None


def slack_delete_workspace(identity: dict | None, team_id: str) -> bool:
    try:
        import psycopg
        from storage import DATABASE_URL
        with psycopg.connect(DATABASE_URL, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM slack_workspaces WHERE owner_key = %s AND team_id = %s",
                        (_owner_key(identity), team_id))
            return cur.rowcount > 0
    except Exception:
        return False


def _slack_error(data: dict) -> RuntimeError:
    """Slack error code -> a sentence a user can act on."""
    code = (data.get("error") or "unknown").strip()
    human = {
        "not_in_channel": "The app is not a member of that conversation — invite it with /invite @Kestrel first.",
        "missing_scope": "The saved access level does not cover this action — reconnect with broader access.",
        "invalid_auth": "The saved Slack token was revoked or rotated — reconnect the workspace.",
        "token_revoked": "The workspace revoked this app — reconnect to restore access.",
        "channel_not_found": "That channel does not exist (or the app cannot see it).",
        "is_archived": "That channel is archived.",
        "ratelimited": "Slack rate-limited the request — try again shortly.",
    }.get(code, code)
    return RuntimeError(human)


def _slack_get(token: str, method: str, params: dict) -> dict:
    """Slack GET with 429 Retry-After backoff (bounded: 2 retries)."""
    import requests
    params = dict(params or {})
    for attempt in range(3):
        r = requests.get(f"https://slack.com/api/{method}",
                         headers={"Authorization": f"Bearer {token}"},
                         params=params, timeout=30)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After") or 2)
            if attempt == 2:
                break
            time.sleep(min(wait, 30))
            continue
        break
    data = r.json()
    if not data.get("ok"):
        raise _slack_error(data)
    return data


def _slack_post_json(token: str, method: str, body: dict) -> dict:
    import requests
    for attempt in range(3):
        r = requests.post(f"https://slack.com/api/{method}",
                          headers={"Authorization": f"Bearer {token}",
                                   "Content-Type": "application/json"},
                          json=body, timeout=30)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After") or 2)
            if attempt == 2:
                break
            time.sleep(min(wait, 30))
            continue
        break
    data = r.json()
    if not data.get("ok"):
        raise _slack_error(data)
    return data


DEMO_SLACK_TEAM_ID = "T_DEMO_ACME"
DEMO_SLACK_TEAM_NAME = "Acme Corp (Demo Workspace)"
DEMO_SLACK_BOT_TOKEN = "demo-slack-bot-token"
DEMO_SLACK_USER_TOKEN = "demo-slack-user-token"
DEMO_SLACK_BOT_USER_ID = "U_KESTREL_BOT"

DEMO_SLACK_CHANNELS = [
    {"id": "C_DEMO_GEN", "name": "general", "private": False, "member": True},
    {"id": "C_DEMO_INC", "name": "incident-postmortems", "private": False, "member": True},
    {"id": "C_DEMO_ROAD", "name": "product-roadmap", "private": False, "member": True},
    {"id": "C_DEMO_SEC", "name": "security-compliance", "private": True, "member": True},
]

DEMO_SLACK_MESSAGES = {
    "C_DEMO_GEN": [
        {"ts": "1728130000.000100", "user": "alice_exec", "text": "Welcome to Acme Corp knowledge workspace! Ensure all team guides and onboarding docs are synced to Kestrel.", "ts_date": "2026-10-05 09:00"},
        {"ts": "1728130500.000200", "user": "bob_eng", "text": "All onboarding guides for engineering and product have been updated.", "ts_date": "2026-10-05 09:15"},
    ],
    "C_DEMO_INC": [
        {"ts": "1728131000.000100", "user": "sarah_ops", "text": "Incident Postmortem #412: On Oct 3, query latency spiked due to Redis connection pool exhaustion. Root cause was an unclosed connection in background worker task. Remediation: pool enlarged to 200, circuit breaker added, p99 back to 42ms.", "ts_date": "2026-10-05 10:00"},
        {"ts": "1728131500.000200", "user": "alex_eng", "text": "Customer SLA credit policy: Affected enterprise customers received an automatic 10% SLA credit in accordance with our 99.9% uptime commitment.", "ts_date": "2026-10-05 10:20"},
    ],
    "C_DEMO_ROAD": [
        {"ts": "1728132000.000100", "user": "priya_pm", "text": "Q4 Roadmap update: Perplexity-style numbered citations and multi-workspace Slack connectors are our top deliverables for enterprise customer presentations.", "ts_date": "2026-10-05 11:00"},
        {"ts": "1728132500.000200", "user": "leo_design", "text": "Citation hover previews and source modal integration are complete. Verified across light and dark modes.", "ts_date": "2026-10-05 11:30"},
    ],
    "C_DEMO_SEC": [
        {"ts": "1728133000.000100", "user": "marc_sec", "text": "SOC2 Audit Policy: API keys, database credentials, and service tokens must remain strictly in environment vaults. Zero secrets committed to source repositories.", "ts_date": "2026-10-05 12:00"},
        {"ts": "1728133500.000200", "user": "devon_eng", "text": "Automated security scanning is active across all commits with check_secrets backstop in CI.", "ts_date": "2026-10-05 12:15"},
    ],
}

_demo_posted_messages: dict[str, list[dict]] = {}

def is_demo_token(token: str | None) -> bool:
    t = (token or "").strip()
    return bool(t and (t.startswith("demo-") or t == DEMO_SLACK_BOT_TOKEN))


def slack_put_demo_workspace(identity: dict | None, mode: str = "read_post", private: bool = False) -> None:
    bot, user = slack_scope_set(mode, private)
    scopes = ",".join(bot)
    tokens = {
        "bot_token": DEMO_SLACK_BOT_TOKEN,
        "user_token": DEMO_SLACK_USER_TOKEN if private else "",
        "bot_user_id": DEMO_SLACK_BOT_USER_ID,
        "access_token": DEMO_SLACK_BOT_TOKEN,
        "team": DEMO_SLACK_TEAM_NAME,
        "team_id": DEMO_SLACK_TEAM_ID,
    }
    slack_put_workspace(
        identity,
        DEMO_SLACK_TEAM_ID,
        DEMO_SLACK_TEAM_NAME,
        tokens,
        scopes,
        mode,
        private,
        bot_user_id=DEMO_SLACK_BOT_USER_ID,
    )
    put_credential("slack", identity, tokens, scopes=scopes)


DEMO_GOOGLE_TOKEN = "ya29.demo-kestrel-google-token"

DEMO_GMAIL_MESSAGES = [
    {
        "id": "msg-001",
        "subject": "Acme Corp SLA & Security Audit Notice",
        "from": "compliance@acmepartners.com",
        "date": "2026-10-04 11:00",
        "body": "Acme Corp has completed the annual SOC2 Type II compliance audit. All data encryption in transit and at rest meets SOC2 requirements. Service Level Agreements guarantee 99.9% availability for all cloud endpoints.",
    },
    {
        "id": "msg-002",
        "subject": "Product Feedback: Citation Verifiability",
        "from": "support@enterpriseclient.com",
        "date": "2026-10-04 14:30",
        "body": "Our executive team requires all AI-generated answers to provide numbered citations linking directly to exact source document excerpts without hallucinations or semantic guessing.",
    },
]


def google_put_demo_credential(identity: dict | None) -> None:
    scopes = " ".join(PROVIDERS["google"]["scopes"])
    tokens = {
        "access_token": DEMO_GOOGLE_TOKEN,
        "refresh_token": "1//demo-refresh",
        "expires_at": int(time.time()) + 86400 * 30,
    }
    put_credential("google", identity, tokens, scopes=scopes)


def slack_channels(token: str, types: str = "public_channel,private_channel", cursor: str = "", limit: int = 100) -> dict:
    if is_demo_token(token):
        chans = [
            c for c in DEMO_SLACK_CHANNELS
            if not c["private"] or ("groups:read" in (types or "") or "private" in (types or ""))
        ]
        return {"channels": chans, "cursor": ""}
    data = _slack_get(token, "conversations.list",
                      {"types": types, "limit": limit,
                       **({"cursor": cursor} if cursor else {}),
                       "exclude_archived": True})
    chans = [{"id": c.get("id"), "name": c.get("name"),
              "private": c.get("is_private", False),
              "member": c.get("is_member", False)}
             for c in data.get("channels", [])]
    return {"channels": chans, "cursor": (data.get("response_metadata") or {}).get("next_cursor", "")}


def slack_history(token: str, channel: str, limit: int = 50, cursor: str = "") -> dict:
    if is_demo_token(token):
        base = list(DEMO_SLACK_MESSAGES.get(channel, []))
        extra = _demo_posted_messages.get(channel, [])
        all_msgs = base + extra
        return {"messages": all_msgs[:limit], "cursor": ""}
    data = _slack_get(token, "conversations.history",
                      {"channel": channel, "limit": limit,
                       **({"cursor": cursor} if cursor else {})})
    msgs = [{"ts": m.get("ts"), "user": m.get("user"), "text": m.get("text", ""),
             "ts_date": time.strftime("%Y-%m-%d %H:%M", time.gmtime(float(m.get("ts", 0) or 0)))}
            for m in data.get("messages", []) if not m.get("subtype")]
    return {"messages": msgs, "cursor": (data.get("response_metadata") or {}).get("next_cursor", "")}


def slack_post(token: str, channel: str, text: str) -> dict:
    if is_demo_token(token):
        now_ts = f"{time.time():.6f}"
        msg = {
            "ts": now_ts,
            "user": "current_user",
            "text": text,
            "ts_date": time.strftime("%Y-%m-%d %H:%M", time.gmtime()),
        }
        _demo_posted_messages.setdefault(channel, []).append(msg)
        return {"ts": now_ts, "channel": channel}
    data = _slack_post_json(token, "chat.postMessage", {"channel": channel, "text": text})
    return {"ts": data.get("ts"), "channel": data.get("channel")}


def slack_revoke(token: str) -> bool:
    if is_demo_token(token):
        return True
    try:
        return bool(_slack_post_json(token, "auth.revoke", {"test": True}).get("ok"))
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


def mint_state(identity: dict | None, provider: str,
               extra: dict | None = None) -> str:
    token = secrets.token_urlsafe(24)
    rec = {"identity": identity or {}, "provider": provider,
           "exp": time.time() + STATE_TTL}
    if extra:
        rec["extra"] = extra
    _states[token] = rec
    # After the insert, so the map never sits above the cap rather than returning to it.
    # The token just minted has the latest expiry, so pruning cannot evict it.
    _prune_states()
    return token


def pop_state(token: str, provider: str) -> dict | None:
    _prune_states()
    rec = _states.pop(token, None)
    if not rec or rec.get("provider") != provider or rec["exp"] < time.time():
        return None
    return rec["identity"]


def pop_state_full(token: str, provider: str) -> dict | None:
    """Whole state record (identity + extra) or None. The scope-picker flow
    needs the extra payload — the choices that were consented to."""
    _prune_states()
    rec = _states.pop(token, None)
    if not rec or rec.get("provider") != provider or rec["exp"] < time.time():
        return None
    return rec


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
        team = data.get("team") or {}
        authed = data.get("authed_user") or {}
        # v2 payload: bot token (workspace-scoped), the authed user's token
        # when user_scopes were requested (DMs), team identity, bot user id.
        return ({
            "access_token": data.get("access_token", ""),
            # Bot tokens do not expire; rotation surfaces as invalid_auth.
            "refresh_token": "",
            "expires_at": 0,
            "team": team.get("name", ""),
            "team_id": team.get("id", ""),
            "bot_token": data.get("access_token", ""),
            "user_token": authed.get("access_token", ""),
            "bot_user_id": data.get("bot_user_id", ""),
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


def refresh_failure(status: int, payload: dict) -> str:
    """Read a token endpoint's refusal as 'revoked', 'config', or 'temporary'.

    Only a dead grant belongs to the user. `invalid_client` / `unauthorized_client`
    mean our own OAuth client is misconfigured — flipping every caller to
    needs_reconnect sends each of them through re-consent while the real fault never
    surfaces. 429/5xx and a body with no recognisable code are provider weather.
    """
    code = str((payload or {}).get("error") or "")
    if code in REVOKED_GRANT_ERRORS:
        return "revoked"
    if code in APPLICATION_CONFIG_ERRORS:
        return "config"
    return "temporary"


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
        if exp and exp <= time.time():
            # Nothing can renew this grant, so a tracked expiry we are already past is
            # a dead token. Handing it back only bought a 401 the caller could not
            # explain, because the row still said 'connected'.
            return None
        return cred["access_token"]  # no expiry tracked: use until refused
    cfg = PROVIDERS["google"]
    try:
        r = requests.post(cfg["token_url"], data={
            "client_id": os.getenv(cfg["client_id_env"], "").strip(),
            "client_secret": os.getenv(cfg["client_secret_env"], "").strip(),
            "grant_type": "refresh_token",
            "refresh_token": refresh,
        }, timeout=30)
        status, data = r.status_code, r.json()
    except Exception:
        # Transport blip (DNS, timeout, 5xx) is NOT a dead grant. Leave the row
        # 'connected' so a flaky network never forces a re-consent, and hand
        # back the stale token — the Gmail call will 401 if it truly died.
        return cred["access_token"]
    if "access_token" not in data:
        outcome = refresh_failure(status, data)
        if outcome == "revoked":
            # Google answered and the grant itself is gone (revoked, or the refresh
            # token was rotated away). The only case that downgrades the row.
            mark_needs_reconnect("google", identity)
        elif outcome == "config":
            # Our application credentials are wrong for EVERY user. Say so at operator
            # level and leave their rows alone — a reconnect prompt cannot fix this.
            # Never log the token or the secret, only the code the provider returned —
            # truncated, because an unbounded provider string in a log line is a
            # newline-injection and rotation hazard.
            log.error("google token refresh refused at the application level "
                      "(error=%.120s, http=%s) — check GOOGLE_OAUTH_CLIENT_ID/"
                      "CLIENT_SECRET; no user connection was changed",
                      str(data.get("error")), status)
        else:
            log.warning("google token refresh deferred (http=%s, error=%.120s) — "
                        "treated as temporary, connection state untouched",
                        status, str(data.get("error")) or "-")
        return None
    fresh = dict(cred)
    fresh["access_token"] = data["access_token"]
    fresh["expires_at"] = int(time.time()) + int(data.get("expires_in") or 3600)
    rotated = bool(data.get("refresh_token"))
    if rotated:
        fresh["refresh_token"] = data["refresh_token"]
    scopes = " ".join(PROVIDERS["google"]["scopes"])
    try:
        put_credential("google", identity, fresh, scopes=scopes)
    except Exception as exc:
        if not rotated:
            # Only the access token moved; the stored refresh token is still current.
            return fresh["access_token"]
        try:
            put_credential("google", identity, fresh, scopes=scopes)
        except Exception as retry_exc:
            # The new refresh token is now the only one Google accepts, and it is not
            # on disk. Serve this request on the access token, say so loudly, and
            # record the loss — without it the owner's row goes stale in silence and
            # they are told to reconnect weeks later with no trace of a cause.
            # No token values are ever logged.
            _rotation_losses.update(count=_rotation_losses["count"] + 1,
                                    owner=_owner_key(identity), at=time.time())
            log.error("google rotated its refresh token and the vault write failed twice "
                      "(%s: %s then %s: %s) — the stored grant for this owner is now "
                      "stale", type(exc).__name__, str(exc)[:120],
                      type(retry_exc).__name__, str(retry_exc)[:120])
        else:
            log.warning("google refresh token rotation persisted on retry after a failed "
                        "first write (%s)", type(exc).__name__)
    return fresh["access_token"]


def slack_token(identity: dict | None) -> str | None:
    """Vault bot token, else legacy env token. Rotation surfaces as
    invalid_auth at call time — callers must map that to needs_reconnect."""
    cred = get_credential("slack", identity)
    if cred and cred.get("_status") == "connected" and cred.get("access_token"):
        return cred["access_token"]
    return os.getenv("SLACK_BOT_TOKEN", "").strip() or None
