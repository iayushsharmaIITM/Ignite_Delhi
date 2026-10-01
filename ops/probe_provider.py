"""Provider probe: prove a model can REALLY generate before activation.

    PYTHONPATH=. python3 ops/probe_provider.py

Probes Amazon Nova Lite on AWS Bedrock's OpenAI-compatible endpoint using
BEDROCK_API_KEY / BEDROCK_REGION / NOVA_LITE_MODEL from .env. The credential
is never printed. Writes var/provider_state.json (the ONLY writer of probe
state) with one of:
    nova_lite_probe_passed
    nova_lite_probe_failed_using_previous_default
Fail-closed contract: llm.py activates the Nova route ONLY when this file
says "nova_lite_probe_passed"; otherwise the previous default stays active.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

# load .env WITHOUT printing anything
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(HERE, ".env"))
except ImportError:
    pass

KEY = os.getenv("BEDROCK_API_KEY", "").strip()
REGIONS = [r for r in os.getenv("BEDROCK_REGION", "us-east-1").split(",") if r]
MODELS = [m for m in os.getenv("NOVA_LITE_MODEL",
          "us.amazon.nova-lite-v1:0,amazon.nova-lite-v1:0").split(",") if m]
PROMPT = "Reply with exactly: NOVA_LITE_OK"
TIMEOUT_S = 60


def probe(region: str, model: str) -> dict:
    url = f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1/chat/completions"
    body = json.dumps({
        "model": model, "max_tokens": 30, "temperature": 0,
        "messages": [{"role": "user", "content": PROMPT}],
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:200]
        return {"ok": False, "reason": f"HTTP {e.code} {detail}",
                "region": region, "model": model, "ms": int((time.time()-t0)*1000)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"[:200],
                "region": region, "model": model, "ms": int((time.time()-t0)*1000)}
    ms = int((time.time() - t0) * 1000)
    content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    resp_model = str(data.get("model", ""))
    # strict validation: real non-empty generation FROM the intended model
    if "NOVA_LITE_OK" not in content:
        return {"ok": False, "reason": f"unexpected completion: {content[:120]!r}",
                "region": region, "model": model, "ms": ms}
    if "nova-lite" not in resp_model:
        return {"ok": False, "reason": f"response model mismatch: {resp_model!r}",
                "region": region, "model": model, "ms": ms}
    return {"ok": True, "region": region, "model": model, "ms": ms,
            "response_model": resp_model}


def main() -> int:
    if not KEY:
        print("PROBE FAILED: BEDROCK_API_KEY missing from .env")
        state = {"nova_lite": "nova_lite_configured_not_verified",
                 "reason": "BEDROCK_API_KEY missing", "ts": _ts()}
        _write(state)
        return 1
    attempts = [probe(r, m) for r in REGIONS for m in MODELS]
    for a in attempts:
        print(("PASS " if a["ok"] else "fail ") +
              f"{a['region']}/{a['model']} ({a.get('ms','?')}ms) {a.get('reason','')}")
    passed = next((a for a in attempts if a["ok"]), None)
    if passed:
        state = {"nova_lite": "nova_lite_probe_passed",
                 "region": passed["region"], "model": passed["model"],
                 "response_model": passed.get("response_model"),
                 "latency_ms": passed["ms"], "ts": _ts()}
        print("NOVA LITE: nova_lite_probe_passed —", passed["region"], passed["model"])
        _write(state)
        return 0
    state = {"nova_lite": "nova_lite_probe_failed_using_previous_default",
             "reason": attempts[0]["reason"], "attempts": len(attempts), "ts": _ts()}
    print("NOVA LITE: nova_lite_probe_failed_using_previous_default — "
          "activation refused; previous default stays active")
    _write(state)
    return 1


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(state: dict) -> None:
    state["probe_prompt"] = PROMPT
    out = os.path.join(HERE, "var", "provider_state.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(state, open(out, "w"), indent=1)
    print("state written:", os.path.relpath(out, HERE))


if __name__ == "__main__":
    sys.exit(main())
