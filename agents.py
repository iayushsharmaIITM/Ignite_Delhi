"""P6 agent layer (Pydantic AI): the answer can ACT.

Two agents, both DeepSeek V4.1 Flash via OpenRouter (OpenAI-compatible),
both with typed outputs so the UI can render real fields instead of prose:

  EmailAgent    — turns an answer (+ its sources) into a sendable email:
                  to, subject, body, sources_used
  MessageAgent  — turns an answer into a Slack-style message: text + channel hint

SEND PATHS (the approval gate is structural): nothing is ever sent by the
agent. The agent only DRAFTS. Sending happens through a separate, explicit
endpoint that Ayush's click triggers, and each transport is env-gated:

  SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS   -> email send (Gmail app-password works)
  SLACK_WEBHOOK_URL                          -> Slack incoming-webhook send
  SLACK_BOT_TOKEN                            -> Slack conversations.history import

Connector imports (Slack history, Gmail IMAP) pull EXTERNAL text into a brain
through the same documents.extract pipeline as uploads, so everything becomes
citable like any other source.
"""

from __future__ import annotations

import os
from typing import List, Optional

from pydantic import BaseModel

import llm

# --- typed outputs -----------------------------------------------------------
class EmailDraft(BaseModel):
    to: str
    subject: str
    body: str
    sources_used: List[str] = []

class MessageDraft(BaseModel):
    channel_hint: str = ""
    text: str

class ConnectorDoc(BaseModel):
    source: str
    text: str


# --- model wiring ------------------------------------------------------------
def _model() -> str:
    return os.getenv("AGENT_MODEL", llm.default_model())


def _make_agent(output_type, system_prompt: str):
    """One DeepSeek agent per call site; the OpenAI-compatible transport
    points at llm.py's resolved endpoint (Token Harbor primary). max_tokens
    is capped: drafts are short, and some gateways pre-authorize max_tokens
    against the account balance — a 32K default gets requests REJECTED on a
    low balance ('can only afford N tokens') even though actual usage is ~1K."""
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from openai import AsyncOpenAI

    key = llm.api_key()
    client = AsyncOpenAI(base_url=llm.base_url(), api_key=key)
    model = OpenAIChatModel(_model(), provider=OpenAIProvider(openai_client=client))
    return Agent(model, output_type=output_type, system_prompt=system_prompt,
                 model_settings={"max_tokens": int(os.getenv("AGENT_MAX_TOKENS", "2000"))})


EMAIL_SYSTEM = (
    "You are Kestrel's email-drafting agent. You receive an answered company "
    "question, its cited sources, and the user's instructions. Draft a concise, "
    "professional email that conveys the answer and attributes facts to the "
    "sources by name. Never invent facts beyond the answer. If the user gave a "
    "recipient, use it; otherwise pick the most plausible owner mentioned."
)

MESSAGE_SYSTEM = (
    "You are Kestrel's messaging agent. Turn the answered question into a "
    "short Slack-style update: tight paragraphs or bullets, facts attributed "
    "to the named sources, no greetings or sign-offs. Never invent facts."
)


async def draft_email(question: str, answer: str, sources: List[str],
                      instructions: str, recipient: Optional[str] = None) -> EmailDraft:
    agent = _make_agent(EmailDraft, EMAIL_SYSTEM)
    prompt = (
        f"Question asked: {question}\n\n"
        f"Answer to convey:\n{answer[:8000]}\n\n"
        f"Sources cited: {', '.join(sources) if sources else 'none'}\n\n"
        f"User instructions: {instructions or 'none'}\n"
        f"Recipient: {recipient or 'choose the most plausible owner from the answer'}"
    )
    result = await agent.run(prompt)
    return result.output


async def draft_message(question: str, answer: str, sources: List[str],
                        instructions: str, channel_hint: str = "") -> MessageDraft:
    agent = _make_agent(MessageDraft, MESSAGE_SYSTEM)
    prompt = (
        f"Question asked: {question}\n\n"
        f"Answer to share:\n{answer[:8000]}\n\n"
        f"Sources cited: {', '.join(sources) if sources else 'none'}\n\n"
        f"User instructions: {instructions or 'none'}\n"
        f"Channel hint: {channel_hint or 'none'}"
    )
    result = await agent.run(prompt)
    return result.output


# --- send transports (env-gated; the approval gate is the explicit call) -----
def email_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"))


def slack_configured() -> bool:
    return bool(os.getenv("SLACK_WEBHOOK_URL"))


def send_email(draft: EmailDraft) -> dict:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user, pwd = os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASS", "")
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = draft.subject, user, draft.to
    msg.attach(MIMEText(draft.body, "plain"))
    body_html = draft.body.replace("\n", "<br>")
    msg.attach(MIMEText(
        f"<div style='font-family:sans-serif;font-size:14px;line-height:1.6'>"
        f"{body_html}</div>", "html"))
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, pwd)
        smtp.sendmail(user, [draft.to], msg.as_string())
    return {"sent": True, "to": draft.to, "subject": draft.subject}


def send_slack(draft: MessageDraft) -> dict:
    import requests
    url = os.getenv("SLACK_WEBHOOK_URL", "")
    r = requests.post(url, json={"text": draft.text}, timeout=20)
    return {"sent": r.status_code == 200, "status": r.status_code}
