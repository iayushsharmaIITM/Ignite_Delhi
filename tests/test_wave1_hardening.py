"""Wave 1 Hardening Tests: Security Headers, Slack HMAC Verification, and Readiness Probes.

Run standalone:
    python3 tests/test_wave1_hardening.py
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PROVIDER"] = "mock"
os.environ["AUTH_MODE"] = "off"
_url = os.environ.get("DATABASE_URL", "")
if _url and "5434" not in _url:
    raise SystemExit("Refusing: DATABASE_URL must point to lab (5434) or be unset.")
if not _url:
    os.environ["DATABASE_URL"] = "postgresql://kestrel:kestrel@127.0.0.1:5434/kestrel"

from cryptography.fernet import Fernet
os.environ.setdefault("CONNECTOR_VAULT_KEY", Fernet.generate_key().decode())
os.environ["SLACK_SIGNING_SECRET"] = "test-signing-secret-kestrel-123"

import app as app_module
import connectors as cx
from fastapi.testclient import TestClient

client = TestClient(app_module.app)
FAILS = []
CHECKS = 0


def check(name: str, ok: bool, detail: str = ""):
    global CHECKS
    CHECKS += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else '  <- ' + detail}")
    if not ok:
        FAILS.append(name)


def main() -> int:
    # 1. Readiness probe /ready
    r_ready = client.get("/api/ready")
    check("GET /api/ready returns 200 with readiness status",
          r_ready.status_code == 200 and r_ready.json().get("ready") is True,
          f"{r_ready.status_code} {r_ready.text}")

    # 2. Enhanced Web Security Headers
    r_health = client.get("/health")
    h = r_health.headers
    check("security headers include X-Content-Type-Options nosniff",
          h.get("X-Content-Type-Options") == "nosniff", str(dict(h)))
    check("security headers include X-Frame-Options SAMEORIGIN",
          h.get("X-Frame-Options") == "SAMEORIGIN", str(dict(h)))
    check("security headers include Permissions-Policy",
          "camera=()" in (h.get("Permissions-Policy") or ""), str(dict(h)))
    check("security headers include Cross-Origin-Opener-Policy",
          h.get("Cross-Origin-Opener-Policy") == "same-origin-allow-popups", str(dict(h)))

    # 3. Slack HMAC-SHA256 Signature Verification
    secret = "test-signing-secret-kestrel-123"
    ts = str(int(time.time()))
    body = b'{"type":"url_verification","challenge":"test-challenge-1234"}'
    basestring = f"v0:{ts}:{body.decode('utf-8')}".encode("utf-8")
    sig = "v0=" + hmac.new(secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()

    # Unit verification in connectors.py
    check("cx.verify_slack_signature verifies valid HMAC signature",
          cx.verify_slack_signature(secret, ts, body, sig) is True)
    check("cx.verify_slack_signature rejects tampered body",
          cx.verify_slack_signature(secret, ts, b'tampered', sig) is False)
    old_ts = str(int(time.time()) - 400)
    old_basestring = f"v0:{old_ts}:{body.decode('utf-8')}".encode("utf-8")
    old_sig = "v0=" + hmac.new(secret.encode("utf-8"), old_basestring, hashlib.sha256).hexdigest()
    check("cx.verify_slack_signature rejects replayed timestamp (>300s)",
          cx.verify_slack_signature(secret, old_ts, body, old_sig) is False)

    # 4. Slack Events endpoint /api/connectors/slack/events
    r_evt = client.post(
        "/api/connectors/slack/events",
        content=body,
        headers={
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": sig,
            "Content-Type": "application/json",
        },
    )
    check("POST /api/connectors/slack/events responds to valid challenge",
          r_evt.status_code == 200 and r_evt.json().get("challenge") == "test-challenge-1234",
          f"{r_evt.status_code} {r_evt.text}")

    r_bad_evt = client.post(
        "/api/connectors/slack/events",
        content=body,
        headers={
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": "v0=invalid-signature-hex",
            "Content-Type": "application/json",
        },
    )
    check("POST /api/connectors/slack/events rejects invalid signature with 401",
          r_bad_evt.status_code == 401,
          f"{r_bad_evt.status_code} {r_bad_evt.text}")

    print("\nWAVE 1 HARDENING TEST:", "FAIL" if FAILS else "PASS")
    if FAILS:
        print(f"  {len(FAILS)} of {CHECKS} checks failed: {', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
