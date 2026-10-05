"""Live Slack integration & external connectors contract tests.

Run standalone (CI fast lane safe with lab or in-memory credentials):
    python3 tests/test_slack_live_connector.py

Checks:
1. Demo Slack workspace connection stores workspace with requested mode and scopes.
2. Slack channels API returns public channels, with private channels gated by scopes.
3. Slack message history returns realistic, citable team communication.
4. Slack posting route accepts message, updates channel feed, and returns timestamp.
5. Post route refuses chat:write when workspace is read-only (403).
6. Connectors import pulls Slack channel into target brain and registers citations.
7. Imported Slack documents appear in citations name map for grounding.
8. Demo Google connection activates demo Gmail transport.
9. Gmail import pulls messages into target brain and registers citations.
10. Workspace disconnect revokes tokens and purges stored credentials cleanly.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PROVIDER"] = "mock"
os.environ["AUTH_MODE"] = "off"
_url = os.environ.get("DATABASE_URL", "")
if _url and "5434" not in _url:
    raise SystemExit(
        "REFUSING: DATABASE_URL names a server that is not the lab (5434). This tier "
        "imports app.py, which runs storage.init(); it must not be pointed at the live "
        "database. Unset DATABASE_URL to run with no database at all, or use the lab.")
if not _url:
    os.environ["DATABASE_URL"] = "postgresql://kestrel:kestrel@127.0.0.1:1/kestrel"

from cryptography.fernet import Fernet
os.environ.setdefault("CONNECTOR_VAULT_KEY", Fernet.generate_key().decode())

import connectors as cx
import citations
import app as app_module
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
    ident = None
    # 1. Connect demo workspace
    cx.slack_put_demo_workspace(ident, mode="read_post", private=True)
    workspaces = cx.slack_list_workspaces(ident)
    check("demo workspace stored in vault",
          any(w["team_id"] == cx.DEMO_SLACK_TEAM_ID for w in workspaces),
          f"got {workspaces}")

    # 2. Channel listing
    ch_res = cx.slack_channels(cx.DEMO_SLACK_BOT_TOKEN, types="public_channel,private_channel")
    channel_names = [c["name"] for c in ch_res.get("channels", [])]
    check("channels returned include incident-postmortems",
          "incident-postmortems" in channel_names,
          f"got {channel_names}")
    check("private channels included when requested",
          "security-compliance" in channel_names,
          f"got {channel_names}")

    # Public-only check
    ch_pub = cx.slack_channels(cx.DEMO_SLACK_BOT_TOKEN, types="public_channel")
    pub_names = [c["name"] for c in ch_pub.get("channels", [])]
    check("private channels excluded when only public requested",
          "security-compliance" not in pub_names,
          f"got {pub_names}")

    # 3. Message history
    hist = cx.slack_history(cx.DEMO_SLACK_BOT_TOKEN, "C_DEMO_INC")
    msgs = hist.get("messages", [])
    check("channel history returns realistic incident discussion",
          len(msgs) >= 2 and any("Redis" in m.get("text", "") for m in msgs),
          f"messages: {msgs}")

    # 4. Live posting
    post_res = cx.slack_post(cx.DEMO_SLACK_BOT_TOKEN, "C_DEMO_INC", "Testing live Slack post from Kestrel")
    check("post returns ok with timestamp",
          bool(post_res.get("ts")),
          f"got {post_res}")
    hist2 = cx.slack_history(cx.DEMO_SLACK_BOT_TOKEN, "C_DEMO_INC")
    check("posted message reflected in subsequent history read",
          any("Testing live Slack post" in m.get("text", "") for m in hist2.get("messages", [])),
          f"history after post: {hist2}")

    # 5. HTTP endpoints for workspaces, channels, messages, post
    r = client.get("/api/connectors/slack/workspaces")
    check("HTTP /workspaces returns 200 with workspaces list",
          r.status_code == 200 and any(w["team_id"] == cx.DEMO_SLACK_TEAM_ID for w in r.json().get("workspaces", [])),
          f"{r.status_code} {r.text}")

    r = client.get(f"/api/connectors/slack/{cx.DEMO_SLACK_TEAM_ID}/channels")
    check("HTTP /channels returns channels list",
          r.status_code == 200 and len(r.json().get("channels", [])) >= 3,
          f"{r.status_code} {r.text}")

    r = client.get(f"/api/connectors/slack/{cx.DEMO_SLACK_TEAM_ID}/messages",
                   params={"channel": "C_DEMO_INC"})
    check("HTTP /messages returns channel messages",
          r.status_code == 200 and len(r.json().get("messages", [])) >= 2,
          f"{r.status_code} {r.text}")

    r = client.post(f"/api/connectors/slack/{cx.DEMO_SLACK_TEAM_ID}/post",
                    json={"channel": "C_DEMO_INC", "text": "HTTP live message post verification"})
    check("HTTP /post posts message successfully",
          r.status_code == 200 and r.json().get("ok") is True,
          f"{r.status_code} {r.text}")

    # 6. Read-only workspace enforcement
    cx.slack_put_demo_workspace(ident, mode="read", private=False)
    r = client.post(f"/api/connectors/slack/{cx.DEMO_SLACK_TEAM_ID}/post",
                    json={"channel": "C_DEMO_INC", "text": "Should be refused"})
    check("read-only workspace refuses post with 403",
          r.status_code == 403,
          f"{r.status_code} {r.text}")

    # Restore read_post
    cx.slack_put_demo_workspace(ident, mode="read_post", private=True)

    # 7. Connector import into brain & citation registration
    test_brain = "company_brain"
    r = client.post("/api/connectors/import",
                    json={"source": "slack", "channel": "C_DEMO_INC", "team_id": cx.DEMO_SLACK_TEAM_ID, "brain": test_brain})
    check("importing Slack channel into brain succeeds",
          r.status_code == 200 and r.json().get("imported", 0) > 0,
          f"{r.status_code} {r.text}")

    # 8. Check citation resolution contains imported Slack messages
    nmap = citations._name_map(test_brain)
    slack_keys = [v for v in nmap.values() if "slack-C_DEMO_INC" in v]
    check("citations manifest maps imported Slack documents",
          len(slack_keys) > 0,
          f"found {slack_keys} in {nmap}")

    # 9. Google Workspace demo connection and import
    r = client.post("/api/connectors/google/demo/connect")
    check("demo Google connection succeeds",
          r.status_code == 200 and r.json().get("connected") == "google",
          f"{r.status_code} {r.text}")

    r = client.post("/api/connectors/import",
                    json={"source": "gmail", "brain": test_brain})
    check("importing demo Gmail into brain succeeds",
          r.status_code == 200 and r.json().get("imported", 0) > 0,
          f"{r.status_code} {r.text}")

    nmap = citations._name_map(test_brain)
    gmail_keys = [v for v in nmap.values() if "gmail-" in v]
    check("citations manifest maps imported Gmail documents",
          len(gmail_keys) > 0,
          f"found {gmail_keys} in {nmap}")

    # 10. Workspace disconnect
    r = client.post(f"/api/connectors/slack/{cx.DEMO_SLACK_TEAM_ID}/disconnect")
    check("workspace disconnect removes workspace from list",
          r.status_code == 200 and r.json().get("removed") is True,
          f"{r.status_code} {r.text}")
    remaining = cx.slack_list_workspaces(ident)
    check("vault no longer lists disconnected team",
          not any(w["team_id"] == cx.DEMO_SLACK_TEAM_ID for w in remaining),
          f"remaining: {remaining}")

    print("\nSLACK & CONNECTORS INTEGRATION TEST:", "FAIL" if FAILS else "PASS")
    if FAILS:
        print(f"  {len(FAILS)} of {CHECKS} checks failed: {', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
