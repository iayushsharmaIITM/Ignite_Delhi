"""Slack-for-general-users: scope building, state burn, permission
enforcement, per-team isolation. In-process TestClient (no network) —
the Slack HTTP layer is stubbed so tests never touch slack.com.

Run: python3 slack_scopes_test.py
"""

from __future__ import annotations

import json
import os
import sys

os.environ["AUTH_MODE"] = "clerk"   # routes resolve real identities via the JWKS stub
from cryptography.fernet import Fernet as _F
os.environ["CONNECTOR_VAULT_KEY"] = _F.generate_key().decode()

PASS, FAIL = [], []


def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print("  PASS ", name)
    except Exception as exc:  # noqa: BLE001
        FAIL.append((name, str(exc)))
        print("  FAIL ", name, "->", str(exc)[:140])


def main():
    import jwt, time
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi.testclient import TestClient
    import app as app_module
    import auth as _auth
    import connectors as cx

    # RS256 session signer + JWKS stub — same shape as the isolation suite
    _KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _KID = "slack-test-kid"
    import base64
    numbers = _KEY.public_key().public_numbers()

    def b64u(i):
        return base64.urlsafe_b64encode(i.to_bytes((i.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()

    jwks = {"keys": [{"kid": _KID, "kty": "RSA", "alg": "RS256", "use": "sig",
                      "n": b64u(numbers.n), "e": b64u(numbers.e)}]}
    TEST_URL = "https://slack-scopes.test/.well-known/jwks.json"
    os.environ["CLERK_JWKS_URL"] = TEST_URL
    _auth._JWKS_TS.clear()
    _auth._JWKS_DATA.clear()
    _auth.inject_jwks_for_test(TEST_URL, jwks)

    def token_for(user):
        return jwt.encode({"sub": user, "o": None,
                           "exp": int(time.time()) + 600,
                           "iat": int(time.time())},
                          _KEY, algorithm="RS256", headers={"kid": _KID})

    client = TestClient(app_module.app)
    H = lambda u: {"Authorization": "Bearer " + token_for(u)}

    # ---- 1. scope building matrix ------------------------------------------
    def sc_matrix():
        bot, user = cx.slack_scope_set("read", False)
        assert "channels:history" in bot and "chat:write" not in bot, bot
        assert user == [], user
        bot, user = cx.slack_scope_set("read_post", False)
        assert "chat:write" in bot and "groups:read" not in bot
        assert user == []
        bot, user = cx.slack_scope_set("read", True)
        assert "groups:history" in bot and "groups:read" in bot
        assert "im:history" in user and "mpim:history" in user
        bot, user = cx.slack_scope_set("read_post", True)
        assert "chat:write" in bot and "groups:history" in bot and "im:history" in user
    check("scope matrix: mode x private", sc_matrix)

    # ---- 2. connect redirect: scopes + user_scope + state in URL ------------
    def sc_redirect():
        os.environ["SLACK_CLIENT_ID"] = "cid-test"
        os.environ["SLACK_CLIENT_SECRET"] = "csec-test"
        r = client.get("/api/connectors/slack/connect?mode=read_post&private=1",
                       headers=H("user_A"), follow_redirects=False)
        assert r.status_code == 302, r.status_code
        loc = r.headers["location"]
        assert "slack.com/oauth/v2/authorize" in loc
        assert "chat%3Awrite" in loc or "chat:write" in loc
        assert "user_scope=im%3Ahistory" in loc or "user_scope=im:history" in loc
        assert "state=" in loc
    check("connect redirect: scopes + user_scope + state", sc_redirect)

    # ---- 3. state burn: one use, wrong provider refused ----------------------
    def sc_state_burn():
        import urllib.parse
        r = client.get("/api/connectors/slack/connect?mode=read",
                       headers=H("user_A"), follow_redirects=False)
        print("  [burn] status:", r.status_code, "| loc:", r.headers.get("location", "")[:60])
        q = urllib.parse.parse_qs(urllib.parse.urlparse(r.headers["location"]).query)
        assert "state" in q, f"no state in redirect: {r.headers['location'][:120]}"
        st = q["state"][0]
        # a WRONG-provider pop burns the state (single-use contract: any pop
        # attempt consumes it — an attacker replaying a state for another
        # provider gains nothing and destroys the original)
        rec = cx.pop_state_full(st, "google")
        assert rec is None, "wrong-provider pop must return None"
        assert cx.pop_state_full(st, "slack") is None, "burned by any pop attempt"
        # fresh state: right provider pops the full payload once
        r2 = client.get("/api/connectors/slack/connect?mode=read_post&private=1",
                        headers=H("user_A"), follow_redirects=False)
        q2 = urllib.parse.parse_qs(urllib.parse.urlparse(r2.headers["location"]).query)
        st2 = q2["state"][0]
        rec = cx.pop_state_full(st2, "slack")
        assert rec is not None, "right-provider pop lost"
        assert rec["extra"]["mode"] == "read_post" and rec["extra"]["private"] is True
        assert cx.pop_state_full(st2, "slack") is None, "single-use"
    check("state: single-use + wrong-provider burn", sc_state_burn)

    # ---- 4. post refused 403 on read-only grant ------------------------------
    def sc_post_403():
        cx.slack_put_workspace({"user_id": "u_T"},
                               "TREAD", "Read Team",
                               {"bot_token": "xoxb-read", "user_token": ""},
                               "channels:read,channels:history", "read", False)
        r = client.post("/api/connectors/slack/TREAD/post",
                        headers=H("u_T"),
                        json={"channel": "C1", "text": "hi"})
        assert r.status_code == 403, (r.status_code, r.text[:100])
        assert "read-only" in r.json()["detail"]
    check("post refused 403 on read-only grant", sc_post_403)

    # ---- 5. post allowed with chat:write (stubbed Slack HTTP) ----------------
    def sc_post_ok():
        cx.slack_put_workspace({"user_id": "u_T"},
                               "TPOST", "Post Team",
                               {"bot_token": "xoxb-post", "user_token": ""},
                               "channels:read,channels:history,chat:write",
                               "read_post", False)
        calls = []
        import connectors as cxm
        orig = cxm._slack_post_json
        cxm._slack_post_json = lambda tok, m, b: calls.append((tok, m, b)) or {"ok": True, "ts": "1", "channel": b["channel"]}
        try:
            r = client.post("/api/connectors/slack/TPOST/post", headers=H("u_T"),
                            json={"channel": "C1", "text": "hello"})
            assert r.status_code == 200, r.text[:120]
            assert calls and calls[0][1] == "chat.postMessage"
            assert calls[0][0] == "xoxb-post"
        finally:
            cxm._slack_post_json = orig
    check("post allowed with chat:write (stubbed transport)", sc_post_ok)

    # ---- 6. per-team isolation -----------------------------------------------
    def sc_isolation():
        r = client.get("/api/connectors/slack/TPOST/channels", headers=H("u_other"))
        # u_other has NO row for TPOST -> 404, never a leak
        assert r.status_code == 404, r.status_code
    check("channels: foreign identity gets 404 (no leak)", sc_isolation)

    # ---- 7. workspaces list hides tokens --------------------------------------
    def sc_no_tokens():
        r = client.get("/api/connectors/slack/workspaces", headers=H("u_T"))
        assert r.status_code == 200
        raw = r.text
        assert "xoxb" not in raw, "token leaked in list!"
        ws = r.json()["workspaces"]
        ids = {w["team_id"] for w in ws}
        assert {"TREAD", "TPOST"} <= ids, f"seeded rows missing: {sorted(ids)}"
        assert all("bot_token" not in w for w in ws)
    check("workspaces list: zero token material", sc_no_tokens)

    # ---- 8. disconnect removes the row ----------------------------------------
    def sc_disconnect():
        cx.slack_put_workspace({"user_id": "u_T"},
                               "TDIS", "D Team", {"bot_token": "xoxb-d", "user_token": ""},
                               "channels:read", "read", False)
        r = client.post("/api/connectors/slack/TDIS/disconnect", headers=H("u_T"))
        assert r.status_code == 200
        assert cx.slack_get_workspace({"org_id": "org_T", "user_id": "u_T"}, "TDIS") is None
    check("disconnect removes the workspace", sc_disconnect)

    # ---- 9. missing workspace -> 404 (not 500) ---------------------------------
    def sc_missing_404():
        r = client.get("/api/connectors/slack/NOPE/channels", headers=H("u_T"))
        assert r.status_code == 404
    check("unknown team -> 404", sc_missing_404)

    # ---- 10. slack error mapping ------------------------------------------------
    def sc_error_map():
        import connectors as cxm
        for code, word in (("not_in_channel", "/invite"),
                           ("missing_scope", "reconnect"),
                           ("token_revoked", "revoke"),
                           ("invalid_auth", "reconnect")):
            try:
                raise cxm._slack_error({"error": code})
            except RuntimeError as e:
                assert word.lower() in str(e).lower(), (code, str(e))
    check("slack error sentences", sc_error_map)

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for name, err in FAIL:
        print("  FAILED:", name, "->", err[:140])
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
