"""P6 connector contract tests — OAuth + vault, run in-process.

Covers the paths that are expensive to get wrong and invisible in a browser:
token-at-rest is ciphertext, refresh rotation works, a revoked grant degrades
to "reconnect" instead of erroring, OAuth state cannot be forged or replayed,
and no secret ever reaches the client.

Run:  python3 connectors_test.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
load_dotenv(os.path.join(HERE, ".env"))

os.environ.setdefault("AUTH_MODE", "off")
os.environ.setdefault("PROVIDER", "mock")
os.environ["PUBLIC_BASE_URL"] = "http://127.0.0.1:8000"
# .env may pin AUTH_MODE=clerk; this suite drives the routes directly, so the
# identity gate must not be the thing under test. Set AFTER load_dotenv.
os.environ["AUTH_MODE"] = "off"

# Fake-but-well-formed OAuth client so the flow has something to bind to.
os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "test.apps.googleusercontent.com"
os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "test-secret"
os.environ["SLACK_CLIENT_ID"] = "123.456"
os.environ["SLACK_CLIENT_SECRET"] = "slack-secret"

# The vault key is minted here, not inherited. Without it every write refuses and
# `/api/connectors/oauth/*/start` answers 503, so the suite only worked on a machine
# whose .env happened to carry a real key — the first hosted CI run failed exactly
# there ("start 302 got=503", then a KeyError on the absent Location header). A test
# key is also a better key: the result no longer depends on whose secret happened to
# be loaded, and nothing here can decrypt anything real.
from cryptography.fernet import Fernet  # noqa: E402

os.environ["CONNECTOR_VAULT_KEY"] = Fernet.generate_key().decode()

import connectors as cx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# AUTH_MODE=off resolves every caller to the single local identity (None),
# so the HTTP flow lands on owner_key "|". The suite asserts against what the
# server actually resolves rather than an invented identity.
IDENT = None
OWNER = cx._owner_key(IDENT)

PASS, FAIL = [], []


def check(label, got, want):
    if got == want:
        PASS.append(label)
        print(f"  PASS  {label}")
    else:
        FAIL.append(label)
        print(f"  FAIL  {label}  got={got!r} want={want!r}")
    return got == want


def truthy(label, value):
    return check(label, bool(value), True)


class _Resp:
    def __init__(self, payload, status=200):
        self._p = payload
        self.status_code = status

    def json(self):
        if isinstance(self._p, Exception):
            raise self._p
        return self._p


def stub_token_endpoint(payload, status=200):
    """Swap connectors' requests.post for the OAuth token call only."""
    seen = {}

    def _post(url, data=None, timeout=None, **kw):
        seen["url"] = url
        seen["data"] = dict(data or {})
        return _Resp(payload, status)

    cx.requests.post = _post
    return seen


def section(name):
    print(f"\n[{name}]")


def main() -> int:
    from app import app

    client = TestClient(app, follow_redirects=False)

    import psycopg
    from storage import DATABASE_URL

    # This suite writes AND deletes rows, and `OWNER` is `|` — the same owner key a
    # single-user install stores its own connected accounts under. It used to take
    # storage.DATABASE_URL with no check, and standalone that is the LIVE tier: the
    # hardcoded default in storage.py:37 points at :5433, and the `connector_credentials`
    # table sitting in the live database is proof this suite has been reaching it. The
    # live vault held 0 rows, so nothing was destroyed — that is luck, not a design.
    if "5434" not in DATABASE_URL:
        print(f"REFUSED: DATABASE_URL resolves to {DATABASE_URL.rsplit('@', 1)[-1]}, "
              "not the lab (5434).")
        print("         This suite deletes connector_credentials rows for owner '|'.")
        print("         Run it against the lab explicitly:")
        print("           DATABASE_URL=<lab 5434> python3 connectors_test.py")
        print("         (./verify.sh does that for you when the lab is up.)")
        sys.exit(2)

    section("vault crypto")
    truthy("vault configured", cx.vault_configured())
    truthy("table ready", cx.init_vault())
    check("unknown provider rejected", cx.provider_configured("nope"), False)
    truthy("google client detected", cx.provider_configured("google"))
    truthy("slack client detected", cx.provider_configured("slack"))
    check("redirect uri", cx.redirect_uri("google"),
          "http://127.0.0.1:8000/api/connectors/oauth/google/callback")

    section("status honesty")
    # A crashed earlier run can leave a row behind; the suite must assert on a
    # known-empty vault, not on whatever the last run happened to write.
    cx.init_vault()
    with psycopg.connect(DATABASE_URL, autocommit=True) as c, c.cursor() as cur:
        cur.execute("DELETE FROM connector_credentials WHERE owner_key = %s", (OWNER,))
    st = client.get("/api/connectors/status")
    check("status 200", st.status_code, 200)
    body = st.json()
    check("google state starts unconfigured",
          body["oauth"]["google"]["state"], "unconfigured")
    check("no gmail read advertised", body["gmail_read"], False)
    check("no slack read advertised", body["slack_read"], False)
    blob = json.dumps(body).lower()
    check("no token material in status", any(
        k in blob for k in ("ya29", "xoxb", "access_token", "refresh")), False)

    section("oauth start -> provider redirect")
    r = client.get("/api/connectors/oauth/google/start")
    check("start 302", r.status_code, 302)
    loc = r.headers["location"]
    check("redirect host", loc.split("?")[0],
          "https://accounts.google.com/o/oauth2/v2/auth")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
    truthy("client_id bound", q.get("client_id", [""])[0])
    check("offline access", q.get("access_type", [""])[0], "offline")
    check("response_type", q.get("response_type", [""])[0], "code")
    truthy("scopes requested", "gmail.readonly" in q.get("scope", [""])[0])
    check("no write scope granted", "gmail.send" in q.get("scope", [""])[0], False)
    truthy("state present", q.get("state", [""])[0])
    state = q["state"][0]

    section("callback guards")
    r = client.get("/api/connectors/oauth/google/callback",
                   params={"code": "x", "state": "forged"})
    check("forged state -> redirect", r.status_code, 302)
    check("forged state -> error", r.headers["location"], "/?connect_error=bad_state")
    r = client.get("/api/connectors/oauth/google/callback", params={"state": state})
    check("no code -> bad_callback", r.headers["location"],
          "/?connect_error=bad_callback")
    r = client.get("/api/connectors/oauth/slack/callback", params={"error": "user_denied"})
    check("provider error surfaced", r.headers["location"],
          "/?connect_error=user_denied")

    # A state token is consumed by ANY pop attempt, right or wrong provider.
    # That is deliberate: an attacker who can probe states must not be able to
    # test one against several providers and keep a live one usable.
    burned = cx.mint_state(IDENT, "google")
    check("wrong provider is rejected", cx.pop_state(burned, "slack"), None)
    check("and burns the token", cx.pop_state(burned, "google"), None)

    section("callback happy path (stubbed token endpoint)")
    seen = stub_token_endpoint({
        "access_token": "ya29.TEST", "refresh_token": "1//TEST",
        "expires_in": 3600, "scope": "openid email gmail.readonly drive.readonly",
    })
    r = client.get("/api/connectors/oauth/google/callback",
                   params={"code": "auth-code", "state": state},
                   follow_redirects=False)
    check("exchange posted to google", seen["url"], cx.PROVIDERS["google"]["token_url"])
    check("grant type", seen["data"].get("grant_type"), "authorization_code")
    check("code forwarded", seen["data"].get("code"), "auth-code")
    check("redirect_uri echoed", seen["data"].get("redirect_uri"),
          cx.redirect_uri("google"))
    check("success redirect", r.headers["location"], "/?connected=google")
    truthy("token never in the redirect body", "ya29" not in r.text)

    cred = cx.get_credential("google", IDENT)
    truthy("credential stored", cred)
    check("token roundtrips", cred["access_token"], "ya29.TEST")
    check("status connected", cred["_status"], "connected")
    truthy("granted scopes persisted", "gmail.readonly" in cred["scopes"])
    check("state is connected", cx.connection_state("google", IDENT), "connected")
    st = client.get("/api/connectors/status").json()
    check("ui sees connected", st["oauth"]["google"]["state"], "connected")
    check("gmail read now advertised", st["gmail_read"], True)

    section("token at rest is ciphertext")
    with psycopg.connect(DATABASE_URL) as c, c.cursor() as cur:
        cur.execute("SELECT blob FROM connector_credentials "
                    "WHERE provider='google' AND owner_key=%s", (OWNER,))
        row = cur.fetchone()
    truthy("row exists", row)
    truthy("blob is fernet", row[0].startswith("gAAAAA"))
    check("plaintext absent at rest", "ya29.TEST" in row[0], False)
    check("refresh token absent at rest", "1//TEST" in row[0], False)

    section("access token lifecycle")
    check("fresh token used as-is", cx.google_access_token(IDENT), "ya29.TEST")
    cx.put_credential("google", IDENT, {"access_token": "ya29.STALE",
                                        "refresh_token": "1//TEST",
                                        "expires_at": int(time.time()) - 10})
    seen = stub_token_endpoint({"access_token": "ya29.ROTATED",
                                "expires_in": 3600, "refresh_token": "1//ROT"})
    check("expired -> silent refresh", cx.google_access_token(IDENT), "ya29.ROTATED")
    check("refresh grant used", seen["data"].get("grant_type"), "refresh_token")
    check("rotation persisted",
          cx.get_credential("google", IDENT)["refresh_token"], "1//ROT")

    stub_token_endpoint({"error": "invalid_grant"})
    cx.put_credential("google", IDENT, {"access_token": "ya29.STALE",
                                        "refresh_token": "1//TEST",
                                        "expires_at": int(time.time()) - 10})
    check("revoked -> no token", cx.google_access_token(IDENT), None)
    check("revoked -> needs reconnect", cx.connection_state("google", IDENT),
          "needs_reconnect")
    check("revoked -> no retry loop", cx.google_access_token(IDENT), None)
    st_body = client.get("/api/connectors/status").json()
    check("ui surfaces reconnect", st_body["oauth"]["google"]["state"],
          "needs_reconnect")
    # A needs_reconnect grant cannot serve an import. Advertising the read
    # transport true here would walk the user straight into a 503.
    check("dead grant does not advertise gmail read", st_body["gmail_read"], False)
    check("client config still reported", st_body["oauth"]["google"]["configured"],
          True)

    stub_token_endpoint(ConnectionError("provider unreachable"))
    cx.put_credential("google", IDENT, {"access_token": "ya29.STALE",
                                        "refresh_token": "1//TEST",
                                        "expires_at": int(time.time()) - 10})
    check("network blip -> stale token", cx.google_access_token(IDENT), "ya29.STALE")
    check("network blip stays connected", cx.connection_state("google", IDENT),
          "connected")

    # An unreadable body is a blip too, for the same reason: the provider answering
    # with garbage is not evidence that THIS user's grant died.
    stub_token_endpoint(ValueError("no json here"))
    cx.put_credential("google", IDENT, {"access_token": "ya29.STALE",
                                        "refresh_token": "1//TEST",
                                        "expires_at": int(time.time()) - 10})
    check("unreadable body -> stale token, same blip rule",
          cx.google_access_token(IDENT), "ya29.STALE")
    check("unreadable body stays connected", cx.connection_state("google", IDENT),
          "connected")

    section("a refusal is not always the user's disconnect")
    # Three different things the token endpoint can say used to collapse into one
    # answer. invalid_client / unauthorized_client mean OUR OAuth client is wrong:
    # flipping every caller to needs_reconnect sent each of them through re-consent
    # while the real fault — a bad GOOGLE_OAUTH_CLIENT_SECRET — never surfaced.
    # 429 and 5xx are provider weather and must not touch anyone's row either.
    def reset_cred(refresh="1//TEST", expires=None):
        cx.put_credential("google", IDENT, {
            "access_token": "ya29.STALE", "refresh_token": refresh,
            "expires_at": expires if expires is not None else int(time.time()) - 10})

    reset_cred()
    stub_token_endpoint({"error": "invalid_client"}, status=401)
    check("client credential refused -> no token", cx.google_access_token(IDENT), None)
    check("client credential refused -> user row NOT flipped",
          cx.connection_state("google", IDENT), "connected")

    reset_cred()
    stub_token_endpoint({"error": "unauthorized_client"}, status=400)
    check("unauthorised client -> no token", cx.google_access_token(IDENT), None)
    check("unauthorised client -> user row stays connected",
          cx.connection_state("google", IDENT), "connected")

    reset_cred()
    stub_token_endpoint({"error": "rate_limit_exceeded"}, status=429)
    check("rate limited -> no token", cx.google_access_token(IDENT), None)
    check("rate limited -> user row stays connected",
          cx.connection_state("google", IDENT), "connected")

    reset_cred()
    stub_token_endpoint({}, status=503)
    check("provider 5xx -> no token", cx.google_access_token(IDENT), None)
    check("provider 5xx -> user row stays connected",
          cx.connection_state("google", IDENT), "connected")

    reset_cred()
    stub_token_endpoint({"error": "invalid_grant"})
    check("a revoked grant STILL flips the row", cx.google_access_token(IDENT), None)
    check("revoked grant still needs reconnect", cx.connection_state("google", IDENT),
          "needs_reconnect")

    section("a grant that cannot be renewed is not handed back expired")
    # With no refresh token nothing can renew this grant, yet a tracked expiry that had
    # already passed was still returned — the caller then took a 401 it could not
    # explain, because the row still said 'connected'. An UNTRACKED expiry keeps
    # meaning 'never expires' (Slack bot tokens, Google grants without expires_in), and
    # those must go on working.
    reset_cred(refresh="", expires=int(time.time()) + 3600)
    check("no refresh token, expiry in the future -> still usable",
          cx.google_access_token(IDENT), "ya29.STALE")
    reset_cred(refresh="", expires=int(time.time()) - 10)
    check("no refresh token, expiry passed -> no token",
          cx.google_access_token(IDENT), None)
    reset_cred(refresh="", expires=0)
    check("no refresh token, no expiry tracked -> unchanged",
          cx.google_access_token(IDENT), "ya29.STALE")

    section("a rotated refresh token is not lost in silence")
    # Google hands back a NEW refresh token on rotation. When the vault write failed the
    # result was `except: pass` — the request was served from the new access token, and
    # the new refresh token was gone forever while the stored one went stale. Weeks
    # later the user is told to reconnect and nothing anywhere says why.
    reset_cred(refresh="1//OLD")
    stub_token_endpoint({"access_token": "ya29.ROTATED", "expires_in": 3600,
                         "refresh_token": "1//NEW"})
    real_put = cx.put_credential
    attempts = {"n": 0}

    def failing_put(*a, **kw):
        attempts["n"] += 1
        raise RuntimeError("vault write refused")

    cx.put_credential = failing_put
    try:
        got = cx.google_access_token(IDENT)
    finally:
        cx.put_credential = real_put
    check("the request is still served with the fresh access token", got, "ya29.ROTATED")
    check("a failed persist is retried once instead of swallowed", attempts["n"], 2)
    truthy("the loss is recorded where an operator can see it",
           cx.rotation_losses()["count"] >= 1)
    check("and the stored grant really is the stale one",
          cx.get_credential("google", IDENT)["refresh_token"], "1//OLD")

    section("oauth state is bounded")
    # mint_state only ever added. Nothing pruned expired states and nothing capped the
    # outstanding set, so abandoned connect clicks accumulated for the life of the
    # process — reproduced at 10,000 retained after their TTL had passed.
    stale = [cx.mint_state(IDENT, "google") for _ in range(25)]
    for t in stale:
        cx._states[t]["exp"] = time.time() - 1   # past the TTL, without waiting it out
    live = cx.mint_state(IDENT, "google")
    truthy("minting prunes what has already expired",
           all(t not in cx._states for t in stale))
    truthy("and keeps the live one", live in cx._states)
    cx.STATE_CAP = 8
    for _ in range(40):
        cx.mint_state(IDENT, "google")
    truthy("outstanding states are capped", len(cx._states) <= 8)
    cx.STATE_CAP = 2000
    cx._states.clear()

    section("state binding")
    s1 = cx.mint_state(IDENT, "google")
    check("state returns to caller", cx.pop_state(s1, "google"), {})
    check("state is single use", cx.pop_state(s1, "google"), None)
    s3 = cx.mint_state(IDENT, "google")
    check("google can still pop it", cx.pop_state(s3, "google"), {})
    s4 = cx.mint_state({"org_id": "org_other", "user_id": "u"}, "google")
    check("state returns the right identity",
          cx.pop_state(s4, "google")["org_id"], "org_other")

    section("isolation between identities")
    org_a = {"org_id": "org_a", "user_id": "user_a"}
    org_b = {"org_id": "org_b", "user_id": "user_b"}
    cx.put_credential("google", org_a, {"access_token": "ya29.A"})
    cx.put_credential("google", org_b, {"access_token": "ya29.B"})
    check("org A reads its own", cx.google_access_token(org_a), "ya29.A")
    check("org B reads its own", cx.google_access_token(org_b), "ya29.B")
    cx.mark_needs_reconnect("google", org_b)
    check("A unaffected by B's revoke", cx.connection_state("google", org_a), "connected")
    check("B downgraded", cx.connection_state("google", org_b), "needs_reconnect")
    check("B's token withheld", cx.google_access_token(org_b), None)
    check("disconnect only own row", cx.delete_credential("google", org_b), True)
    check("A survives B disconnecting", cx.google_access_token(org_a), "ya29.A")
    cx.delete_credential("google", org_a)
    with psycopg.connect(DATABASE_URL, autocommit=True) as c, c.cursor() as cur:
        cur.execute("DELETE FROM connector_credentials WHERE owner_key IN (%s, %s)",
                    (cx._owner_key(org_a), cx._owner_key(org_b)))

    section("slack connect")
    cx._states.clear()
    r = client.get("/api/connectors/oauth/slack/start")
    loc = urllib.parse.urlparse(r.headers["location"])
    check("slack authorize path", loc.path, "/oauth/v2/authorize")
    check("slack host", loc.netloc, "slack.com")
    sq = urllib.parse.parse_qs(loc.query)
    truthy("slack scopes", "channels:history" in sq.get("scope", [""])[0])
    check("no chat:write in read grant", "chat:write" in sq.get("scope", [""])[0], False)
    sstate = sq["state"][0]
    stub_token_endpoint({"ok": True, "access_token": "xoxb-TEST",
                         "team": {"name": "Acme"}, "scope": "channels:history,channels:read"})
    r = client.get("/api/connectors/oauth/slack/callback",
                   params={"code": "c", "state": sstate})
    check("slack success redirect", r.headers["location"], "/?connected=slack")
    check("slack token stored", cx.get_credential("slack", IDENT)["access_token"],
          "xoxb-TEST")
    check("slack team recorded",
          cx.get_credential("slack", IDENT)["extra"].get("team"), "Acme")
    stub_token_endpoint({"ok": False, "error": "invalid_code"})
    r = client.get("/api/connectors/oauth/slack/callback",
                   params={"code": "c", "state": "forged"})
    check("slack bad state still guarded", r.headers["location"],
          "/?connect_error=bad_state")
    check("slack token resolved", cx.slack_token(IDENT), "xoxb-TEST")
    check("live slack grant advertises read",
          client.get("/api/connectors/status").json()["slack_read"], True)
    os.environ["SLACK_BOT_TOKEN"] = "xoxb-env"
    check("vault beats env", cx.slack_token(IDENT), "xoxb-TEST")
    cx.mark_needs_reconnect("slack", IDENT)
    check("reconnect falls back to env", cx.slack_token(IDENT), "xoxb-env")
    st_body = client.get("/api/connectors/status").json()
    check("slack state is reconnect", st_body["oauth"]["slack"]["state"],
          "needs_reconnect")
    check("dead slack grant does not advertise read", st_body["slack_read"], False)
    check("but the env token alone does", cx.slack_token(IDENT), "xoxb-env")
    del os.environ["SLACK_BOT_TOKEN"]

    section("disconnect")
    r = client.post("/api/connectors/disconnect", json={"provider": "google"})
    check("disconnect 200", r.status_code, 200)
    check("disconnect ok", r.json()["ok"], True)
    check("row gone", cx.get_credential("google", IDENT), None)
    check("state unconfigured", cx.connection_state("google", IDENT), "unconfigured")
    r = client.post("/api/connectors/disconnect", json={"provider": "google"})
    check("second disconnect is a no-op", r.json()["ok"], False)
    r = client.post("/api/connectors/disconnect", json={"provider": "dropbox"})
    check("unknown provider rejected", r.status_code, 400)
    cx.delete_credential("slack", IDENT)

    section("no key at all -> reads degrade, writes refuse")
    saved = os.environ.pop("CONNECTOR_VAULT_KEY", None)
    try:
        check("vault reported unconfigured", cx.vault_configured(), False)
        check("init is a no-op", cx.init_vault(), False)
        check("state unconfigured", cx.connection_state("google", IDENT), "unconfigured")
        try:
            cx.put_credential("google", IDENT, {"access_token": "leak"})
            check("write refused without a key", False, True)
        except RuntimeError:
            check("write refused without a key", True, True)
    finally:
        if saved:
            os.environ["CONNECTOR_VAULT_KEY"] = saved

    with psycopg.connect(DATABASE_URL, autocommit=True) as c, c.cursor() as cur:
        cur.execute("DELETE FROM connector_credentials WHERE owner_key=%s", (OWNER,))

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
