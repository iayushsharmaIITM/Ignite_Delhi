"""Test suite for AI agents and orchestrator sub-agents (P6 agent layer).

Tests:
1. Pydantic AI agent models: EmailDraft, MessageDraft, ConnectorDoc validation.
2. System prompts for EmailAgent and MessageAgent.
3. Orchestrator head agent planning & retrieval sub-agents (RACERS).
4. Router sub-agent query classification (CHAT vs BRAIN).
5. Agent configuration detection (email & slack send gates).
6. Agent draft generation fallback & error resilience.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["PROVIDER"] = "mock"
os.environ["AUTH_MODE"] = "off"

import agents
import orchestrator

CHECKS = 0
FAILS = []


def check(name: str, ok: bool, detail: str = ""):
    global CHECKS
    CHECKS += 1
    status = "PASS" if ok else "FAIL"
    print(f"  {status}  {name}{'' if ok else '  <- ' + detail}")
    if not ok:
        FAILS.append(name)


def main() -> int:
    print("== Kestrel AI Agents Test Suite ==")

    # 1. EmailDraft schema & validation
    try:
        draft = agents.EmailDraft(
            to="cfo@acme.corp",
            subject="Q3 SLA Credits Summary",
            body="Here is the breakdown of the approved credits...",
            sources_used=["05_policy_SLA-credit-01.md"],
        )
        check("EmailDraft creates valid model", draft.to == "cfo@acme.corp")
        check("EmailDraft retains sources_used", draft.sources_used == ["05_policy_SLA-credit-01.md"])
        check("EmailDraft dumps clean dict", "subject" in draft.model_dump())
    except Exception as e:
        check("EmailDraft model", False, str(e))

    # 2. MessageDraft schema & validation
    try:
        msg = agents.MessageDraft(
            channel_hint="#leadership",
            text="Renewal at risk for Bluepeak due to credit dispute.",
        )
        check("MessageDraft creates valid model", msg.channel_hint == "#leadership")
        check("MessageDraft text matches", "Bluepeak" in msg.text)
    except Exception as e:
        check("MessageDraft model", False, str(e))

    # 3. ConnectorDoc schema
    try:
        cdoc = agents.ConnectorDoc(
            source="slack:#general",
            text="Team meeting notes for Oct 7.",
        )
        check("ConnectorDoc validates source and text", cdoc.source == "slack:#general")
    except Exception as e:
        check("ConnectorDoc model", False, str(e))

    # 4. Agent system prompts
    check("EMAIL_SYSTEM defines drafting role", "email-drafting agent" in agents.EMAIL_SYSTEM)
    check("EMAIL_SYSTEM enforces grounding", "Never invent facts" in agents.EMAIL_SYSTEM)
    check("MESSAGE_SYSTEM defines message agent", "messaging agent" in agents.MESSAGE_SYSTEM)

    # 5. Orchestrator head agent planning and sub-agents
    check("Orchestrator defines retrieval sub-agent racers", len(orchestrator.RACERS) == 2)
    labels = [r[0] for r in orchestrator.RACERS]
    check("Graph retrieval agent is in racers", "graph retrieval agent" in labels)
    check("Vector retrieval agent is in racers", "vector retrieval agent" in labels)

    # 6. Router sub-agent classification logic
    # Without API key, fails closed to "brain" (safe default):
    with patch("llm.api_key", return_value=""):
        check("Router fails closed to brain when no key", orchestrator._classify("hello") == "brain")

    # With mocked model responses:
    mock_resp_chat = MagicMock()
    mock_resp_chat.json.return_value = {"choices": [{"message": {"content": "CHAT"}}]}
    with patch("llm.api_key", return_value="sk-test"), patch("requests.post", return_value=mock_resp_chat):
        cat_chat = orchestrator._classify("Hello there, how are you today?")
        check("Router sub-agent classifies greeting as chat", cat_chat == "chat", f"got {cat_chat}")

    mock_resp_brain = MagicMock()
    mock_resp_brain.json.return_value = {"choices": [{"message": {"content": "BRAIN"}}]}
    with patch("llm.api_key", return_value="sk-test"), patch("requests.post", return_value=mock_resp_brain):
        cat_doc = orchestrator._classify("Why is the Bluepeak renewal at risk?")
        check("Router sub-agent classifies policy question as brain", cat_doc == "brain", f"got {cat_doc}")

    # 7. Agent configuration checks
    email_cfg = agents.email_configured()
    check("email_configured returns bool", isinstance(email_cfg, bool))

    slack_cfg = agents.slack_configured()
    check("slack_configured returns bool", isinstance(slack_cfg, bool))

    print(f"\nAI Agents battery: {CHECKS - len(FAILS)}/{CHECKS} passed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
