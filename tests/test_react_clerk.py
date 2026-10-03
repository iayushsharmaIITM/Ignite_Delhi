"""Phase B proof gate: the served React app works with AUTH_MODE=clerk.

    DATABASE_URL=postgresql://kestrel:kestrel@localhost:5434/kestrel \
        python3 tests/test_react_clerk.py

Why this exists
---------------
The port shipped looking green because its dev server proxied to the auth-off
lab twin (:8010), where every route waves the caller through. On the live stack
(`.env`: AUTH_MODE=clerk) nearly every React API call went out without an
Authorization header and 401'd — rendered to the user as "No saved chats yet".
No test could see it: the UI suite only ever ran against auth-off.

What it does
------------
Two halves that cannot drift apart:

  contract  the API rule, in-process, using the documented seam
            `auth.inject_jwks_for_test` (the same one tests/test_route_authz.py
            uses): a signed token is 200, no token is 401
  browser   boots the REAL app (`python app.py`) with KESTREL_UI=react,
            AUTH_MODE=clerk and a JWKS endpoint it serves itself (a subprocess
            cannot be injected into, so this half speaks real HTTP), then drives
            the served bundle with Playwright twice:

  positive  window.Clerk.session.getToken() returns a signed test JWT
            → /api/brains + /api/chats are 200, every /api request carries a
              Bearer token, an ask streams an answer, a follow-up carries the
              conversation context, and an ask that fails renders the server's
              own words in a .bubble.err state with the composer freed
  control   the same page with a session that cannot mint a token
            → the same requests 401 and the UI shows the server's own words

The control is the point: without it the positive run could pass for the wrong
reason (auth off, or a route that forgot its gate). Both runs must behave as
described or the gate fails.

Runs against the LAB database only (asserts 5434) — it creates a chat, and the
live database is not a test fixture.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if "5434" not in DATABASE_URL:
    print("REFUSING: set DATABASE_URL to the lab database (port 5434). This "
          "test writes a chat and must not touch live.")
    sys.exit(2)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright is required: pip install -r requirements-dev.txt")
    sys.exit(2)

import jwt as pyjwt  # noqa: E402
import psycopg  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

ISSUER = "https://clerk.test"
APP_PORT = int(os.environ.get("KESTREL_TEST_PORT", "8031"))
BASE = f"http://127.0.0.1:{APP_PORT}"

# --------------------------------------------------------------------------
# Test identity: an RSA keypair, its public JWKS, and a signed session token
# --------------------------------------------------------------------------
priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
pub = priv.public_key().public_numbers()


def _b64u(n: int) -> str:
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


JWKS = {"keys": [{"kty": "RSA", "alg": "RS256", "use": "sig", "kid": "t",
                  "n": _b64u(pub.n), "e": _b64u(pub.e)}]}


class JwksHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server API
        body = json.dumps(JWKS).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep the test output clean
        pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def owner_identity() -> tuple[str, str]:
    """The org/user that owns the demo brain in the lab DB.

    Authorization is fail-closed: a brain with no access row 403s for everyone,
    so a made-up org would test the deny path, not the allow path.
    """
    with psycopg.connect(DATABASE_URL, row_factory=psycopg.rows.dict_row) as c, c.cursor() as cur:
        row = cur.execute(
            "select org_id, created_by from brain_access "
            "where brain = 'company_brain' limit 1"
        ).fetchone()
    if not row or not row["org_id"]:
        print("REFUSING: no brain_access row for company_brain in the lab DB — "
              "run the backfill/seed first; the allow path cannot be tested.")
        sys.exit(2)
    return row["org_id"], row["created_by"] or "user_test"


def token(org_id: str, user_id: str, ttl: int = 600) -> str:
    return pyjwt.encode(
        {"sub": user_id, "iss": ISSUER, "exp": time.time() + ttl,
         "o": {"id": org_id}},
        priv, algorithm="RS256", headers={"kid": "t"},
    )


def wait_for(url: str, seconds: int = 30) -> bool:
    for _ in range(seconds * 2):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.5)
    return False


# --------------------------------------------------------------------------
# Clerk stub: what clerk.browser.js would put on window, minus the network
# --------------------------------------------------------------------------
CLERK_STUB = """
(args) => {
  const token = args.token;
  const signedIn = !!token;
  window.Clerk = {
    loaded: true,
    session: signedIn ? { getToken: async () => token } : null,
    client: { sessions: signedIn ? [{ getToken: async () => token }] : [] },
    user: signedIn ? { firstName: 'Test', lastName: 'User',
                       primaryEmailAddress: 'test@example.com' } : null,
    addListener() {}, openSignIn() {}, closeSignIn() {},
    signOut: async () => {}, openUserProfile() {},
  };
}
"""


def run_browser(signed_in: bool, jwt_token: str, failures: list[str]) -> dict:
    """Drive the served app; return observed API statuses + UI facts."""
    seen: dict[str, int] = {}
    bearer: dict[str, str] = {}
    console: list[str] = []
    ask_urls: list[str] = []
    result: dict = {}

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception:  # noqa: BLE001 - fall back to the bundled chromium
            browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.add_init_script(f"({CLERK_STUB})({{ token: {json.dumps(jwt_token)} }})")

        def on_response(resp):
            url = resp.url
            if "/api/" in url:
                path = url.split("/api/", 1)[1].split("?")[0]
                seen[path] = resp.status

        def on_request(req):
            if "/api/" in req.url:
                path = req.url.split("/api/", 1)[1].split("?")[0]
                hdrs = req.headers
                if hdrs.get("authorization"):
                    bearer[path] = hdrs["authorization"]
                if path == "ask":
                    ask_urls.append(req.url)

        page.on("response", on_response)
        page.on("request", on_request)
        page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console.append(str(e)))

        try:
            page.goto(BASE + "/", wait_until="networkidle")
            page.wait_for_timeout(1500)

            result["react_served"] = page.locator("#root").count() == 1
            result["body_text"] = page.inner_text("body")[:4000]
            result["api"] = dict(seen)
            result["bearer"] = dict(bearer)
            result["console"] = list(console)

            if signed_in:
                # 1. an ask streams a turn through the served bundle
                page.fill("#q", "What is the Bluepeak renewal status?")
                page.press("#q", "Enter")
                page.wait_for_timeout(6000)
                bubbles = page.locator(".turn.bot .bubble")
                result["bot_turns"] = bubbles.count()
                result["answer"] = (bubbles.last.text_content() or "")[:400] if bubbles.count() else ""
                result["ask_status"] = seen.get("ask")
                result["console_after_ask"] = list(console)

                # 2. a follow-up carries the conversation (B3): without
                #    `context` every question is a cold start.
                page.fill("#q", "And who signs it off?")
                page.press("#q", "Enter")
                page.wait_for_timeout(6000)
                result["ask_urls"] = list(ask_urls)
                result["follow_up_has_context"] = any(
                    "context=" in u and "Earlier" in u for u in ask_urls[1:]
                )

                # 3. a failing ask is reported, not rendered as a blank answer
                #    (B2). Intercept the stream with the live server's own 401.
                page.route(
                    "**/api/ask*",
                    lambda route: route.fulfill(
                        status=401,
                        content_type="application/json",
                        body=json.dumps({"detail": "A valid Clerk session token is required."}),
                    ),
                )
                page.fill("#q", "Does a failed ask say so?")
                page.press("#q", "Enter")
                page.wait_for_timeout(2500)
                err_bubbles = page.locator(".turn.bot .bubble.err")
                result["error_bubbles"] = err_bubbles.count()
                result["error_text"] = (
                    (err_bubbles.last.text_content() or "")[:300] if err_bubbles.count() else ""
                )
                # the composer must be usable again (not stuck in "stop")
                result["composer_usable"] = page.locator("#go.stop").count() == 0
                page.unroute("**/api/ask*")
        finally:
            browser.close()

    if not result.get("react_served"):
        failures.append("react bundle was not served at /")
    return result


def in_process_contract(good: str) -> tuple[int, int]:
    """Pin the API contract in-process, using auth.inject_jwks_for_test.

    The browser half of this gate needs a real server, so it serves its own
    JWKS over HTTP. This half uses the documented test seam instead — the same
    path tests/test_route_authz.py and tests/test_v2_authz.py use — so the
    server-side rule ("a signed Clerk token is required") is pinned without a
    browser, and the two halves cannot drift apart.

    Returns (status with a valid token, status without one).
    """
    os.environ["AUTH_MODE"] = "clerk"
    os.environ.setdefault("CLERK_JWKS_URL", "http://jwks.test/keys")
    os.environ["CLERK_ISSUER"] = ISSUER

    import auth  # noqa: PLC0415 - imported after the env is set, by design
    auth.inject_jwks_for_test(os.environ["CLERK_JWKS_URL"], JWKS)

    from fastapi.testclient import TestClient  # noqa: PLC0415
    import app as app_module  # noqa: PLC0415

    client = TestClient(app_module.app)
    with_token = client.get("/api/brains", headers={"Authorization": f"Bearer {good}"}).status_code
    without = client.get("/api/brains").status_code
    return with_token, without


def main() -> int:
    failures: list[str] = []
    org_id, user_id = owner_identity()
    good_token = token(org_id, user_id)

    print("[contract] in-process, auth.inject_jwks_for_test")
    with_token, without = in_process_contract(good_token)
    print(f"  /api/brains with a signed token: {with_token} | without: {without}")
    if with_token != 200:
        failures.append(f"contract: a signed Clerk token got {with_token}, expected 200")
    if without != 401:
        failures.append(f"contract: no token got {without}, expected 401")

    jwks_port = free_port()
    jwks = ThreadingHTTPServer(("127.0.0.1", jwks_port), JwksHandler)
    threading.Thread(target=jwks.serve_forever, daemon=True).start()

    env = dict(os.environ)
    env.update({
        "AUTH_MODE": "clerk",
        "CLERK_JWKS_URL": f"http://127.0.0.1:{jwks_port}/keys",
        "CLERK_ISSUER": ISSUER,
        "CLERK_PUBLISHABLE_KEY": "pk_test_phase_b_gate",
        "KESTREL_UI": "react",
        "PROVIDER": "mock",
        "DATABASE_URL": DATABASE_URL,
        "PORT": str(APP_PORT),
        "HOST": "127.0.0.1",
    })
    log = open("/tmp/kestrel_react_clerk.log", "w")
    app = subprocess.Popen([sys.executable, "app.py"], env=env, stdout=log,
                           stderr=subprocess.STDOUT, cwd=os.path.dirname(
                               os.path.dirname(os.path.abspath(__file__))))

    try:
        if not wait_for(BASE + "/health"):
            print("FAIL: app did not come up — see /tmp/kestrel_react_clerk.log")
            return 1
        print(f"app up on {BASE} (AUTH_MODE=clerk, KESTREL_UI=react, PROVIDER=mock)\n")

        print("[positive] signing in with a real signed JWT")
        pos = run_browser(True, good_token, failures)
        print("  api:", pos.get("api"))
        for path, expect in (("brains", 200), ("chats", 200)):
            got = pos.get("api", {}).get(path)
            if got != expect:
                failures.append(f"positive: /api/{path} was {got}, expected {expect}")
        if pos.get("ask_status") != 200:
            failures.append(f"positive: /api/ask was {pos.get('ask_status')}, expected 200")
        if not all(v.lower().startswith("bearer ") for v in pos.get("bearer", {}).values()):
            failures.append("positive: an /api request went out without a Bearer token")
        if pos.get("bot_turns", 0) < 1 or not (pos.get("answer") or "").strip():
            failures.append("positive: the ask produced no answer text in the thread")
        if not pos.get("follow_up_has_context"):
            failures.append("positive: the follow-up ask carried no conversation "
                            "context (B3) — every question would be a cold start")
        if pos.get("error_bubbles", 0) < 1:
            failures.append("positive: a failing ask rendered no .bubble.err state (B2)")
        elif "Clerk session token" not in (pos.get("error_text") or ""):
            failures.append("positive: the failed ask did not quote the server "
                            f"(got {(pos.get('error_text') or '')[:80]!r})")
        if not pos.get("composer_usable"):
            failures.append("positive: the composer stayed in the stop state after a "
                            "failed ask")
        if pos.get("console_after_ask"):
            failures.append(f"positive: console errors: {pos['console_after_ask'][:2]}")

        print("[control] same page, a session that cannot mint a token")
        ctl = run_browser(False, "", failures)
        print("  api:", ctl.get("api"))
        for path, expect in (("brains", 401), ("chats", 401)):
            got = ctl.get("api", {}).get(path)
            if got != expect:
                failures.append(f"control: /api/{path} was {got}, expected {expect}")
        # The honest-state assertion: the server's own words, not an empty list.
        body = ctl.get("body_text", "")
        if "Clerk session token" not in body:
            failures.append("control: the 401 was not surfaced in the UI "
                            "(expected the server's own message on screen)")
        if "No saved chats yet" in body:
            failures.append("control: still rendered the misleading empty-chats state")
    finally:
        app.terminate()
        try:
            app.wait(timeout=10)
        except subprocess.TimeoutExpired:
            app.kill()
        jwks.shutdown()
        log.close()

    print()
    if failures:
        print(f"{len(failures)} FAILED:")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS — the served React app is authenticated in clerk mode, and the "
          "same page without a token 401s with the server's own words on screen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
