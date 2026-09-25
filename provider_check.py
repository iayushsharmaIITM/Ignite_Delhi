"""Warm-route checker: prove every provider route in the registry is usable.

BUILD_PLAN M1.1 follow-up (human request 2026-09-25): "all the API routes for
all the providers warm, so I can provide a key whenever I want."

For each registry provider this fires a tiny real request with a dummy key
(or the live key when one is configured) and CLASSIFIES the failure:

  WARM   the request reached the provider and was rejected only on
         credentials/account grounds (401, permission, quota, verification)
         — pasting a valid key is all that remains
  COLD   the route itself is wrong (unknown model, bad endpoint shape)
  SKIP   provider dormant by design (e.g. keyless Ollama with service stopped)

Run inside the container (it has litellm):

    docker exec -i cognee-oss python - < provider_check.py
    # or: docker exec cognee-oss python /path/to/provider_check.py

The live key (if any) comes from the container env; dummy keys are invented
here. No secrets are printed.
"""

import os

import litellm

DUMMY = "sk-warmcheck-dummy-not-a-real-key"

# name -> (litellm model string, base_url, api_key, note)
PROVIDERS = {
    "openai": ("openai/gpt-4o-mini", None, DUMMY, "dummy key -> expect 401"),
    "azure": ("azure/gpt-4o-mini", "https://warmcheck-endpoint.cognitiveservices.azure.com/",
              DUMMY, "dummy endpoint+key -> expect 401"),
    "openrouter": ("openai/gpt-oss-120b", "https://openrouter.ai/api/v1",
                   os.environ.get("LLM_API_KEY") or DUMMY, "live key configured"),
    "groq": ("openai/gpt-oss-120b", "https://api.groq.com/openai/v1", DUMMY, "dummy key -> expect 401"),
    "cerebras": ("openai/gpt-oss-120b", "https://api.cerebras.ai/v1", DUMMY, "dummy key -> expect 401"),
    "anthropic": ("anthropic/claude-sonnet-4-20250514", None, DUMMY, "dummy key -> expect 401"),
    "bedrock": ("bedrock/openai.gpt-oss-120b-1:0", None, None,
                "real bearer key in env; account pending verification"),
    "deepseek": ("deepseek/deepseek-chat", "https://api.deepseek.com/v1", DUMMY, "dummy key -> expect 401"),
    "zai": ("zai/glm-4.6", "https://api.z.ai/api/paas/v4", DUMMY, "dummy key -> expect 401"),
}

WARM_MARKS = ("401", "unauthorized", "authentication", "invalid", "permission",
              "not allowed", "being verified", "quota", "billing", "rate limit",
              "credit", "api key")
COLD_MARKS = ("unknown model", "not found", "does not exist", "unsupported model",
              "no provider", "unsupported parameter")


def classify(model: str, base_url: str | None, key: str | None) -> str:
    kwargs = {"messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 5, "timeout": 45}
    if key:
        kwargs["api_key"] = key
    if base_url:
        kwargs["base_url"] = base_url
        kwargs["custom_llm_provider"] = "openai"  # OpenAI-compatible route
    try:
        litellm.completion(model=model, **kwargs)
        return "LIVE"          # fully working — only possible with a real key
    except Exception as exc:  # noqa: BLE001
        text = str(exc).lower()
        if any(m in text for m in COLD_MARKS):
            return "COLD"
        if any(m in text for m in WARM_MARKS):
            return "WARM"
        return f"UNKNOWN: {str(exc)[:80]}"


print(f"{'provider':<12} {'verdict':<10} detail")
print("-" * 66)
warm = 0
for name, (model, base_url, key, note) in PROVIDERS.items():
    if name == "ollama":
        print(f"{name:<12} {'SKIP':<10} dormant by design (models removed; see .env.oss)")
        continue
    verdict = classify(model, base_url, key)
    if name == "azure" and verdict.startswith("UNKNOWN"):
        # A dummy hostname never reaches the provider's 401, so a live probe
        # cannot classify Azure. Verify instead that litellm fully maps the
        # model string + required params — the endpoint is only testable once
        # the human's real Azure OpenAI resource exists.
        try:
            info = litellm.get_model_info(model)
            verdict = f"CONFIG-WARM (max_tokens={info.get('max_input_tokens')}; endpoint testable when the resource exists)"
        except Exception as exc:  # noqa: BLE001
            verdict = f"COLD: {str(exc)[:80]}"
    if verdict == "WARM":
        warm += 1
    print(f"{name:<12} {verdict:<10} {note}")
print("-" * 66)
print(f"{warm} route(s) WARM — a valid key is the only missing piece for those.")
