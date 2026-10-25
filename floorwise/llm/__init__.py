"""Provider-neutral LLM layer. Production runs on Claude; until credits arrive, tests can run on any
OpenAI-compatible provider (Groq, OpenRouter). Pick with FLOORWISE_PROVIDER=anthropic|groq|openrouter.

Roles and default models:
  chat    the conversational agent with tools
  parser  question -> QuerySpec (structured output)
  vision  room labels from plan images
  judge   grading transcripts in evals"""

import os
from dataclasses import dataclass

PROVIDERS = {
    "anthropic": {
        "chat": "claude-sonnet-5-5", "parser": "claude-haiku-5-5", "vision": "claude-opus-5-5", "judge": "claude-opus-5-5",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY",
        "chat": "openai/gpt-oss-120b", "parser": "qwen/qwen3.8-27b", "vision": None, "judge": "openai/gpt-oss-120b",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY",
        "chat": "openai/gpt-oss-120b", "parser": "qwen/qwen3.8-27b", "vision": None, "judge": "openai/gpt-oss-120b",
    },
}


@dataclass
class ProviderInfo:
    name: str
    available: bool
    models: dict
    reason: str = ""


def provider_name() -> str:
    explicit = os.environ.get("FLOORWISE_PROVIDER")
    if explicit:
        return explicit
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "anthropic"
    for name in ("groq", "openrouter"):
        if os.environ.get(PROVIDERS[name]["key_env"]):
            return name
    return "anthropic"


def model_for(role: str, provider: str | None = None) -> str | None:
    provider = provider or provider_name()
    override = os.environ.get(f"FLOORWISE_{role.upper()}_MODEL")
    return override or PROVIDERS[provider].get(role)


def info() -> ProviderInfo:
    name = provider_name()
    config = PROVIDERS.get(name, {})
    if name == "anthropic":
        ok = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    else:
        ok = bool(os.environ.get(config.get("key_env", "")))
    models = {role: model_for(role, name) for role in ("chat", "parser", "vision", "judge")}
    return ProviderInfo(name, ok, models, "" if ok else f"no API key for {name} in .env")


def client(provider: str | None = None):
    """SDK client for the provider: anthropic.Anthropic or openai.OpenAI (compatible endpoint)."""
    if os.environ.get('FLOORWISE_OFFLINE') == '1':
        raise RuntimeError('Live model calls are disabled in the offline test profile.')
    provider = provider or provider_name()
    from floorwise.llm.budget import timeout_s, retries

    if provider == "anthropic":
        import anthropic

        key = os.environ.get("ANTHROPIC_API_KEY")
        token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if not key and not token and not os.environ.get("FLOORWISE_ANTHROPIC_PROFILE"):
            raise KeyError("no API key for anthropic in .env (set ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN)")
        if not key and not token:  # the SDK finds the logged-in Claude profile on its own
            return anthropic.Anthropic(timeout=timeout_s(), max_retries=retries())
        return anthropic.Anthropic(api_key=key, auth_token=None if key else token, timeout=timeout_s(), max_retries=retries())
    import openai

    config = PROVIDERS[provider]
    return openai.OpenAI(base_url=config["base_url"], api_key=os.environ[config["key_env"]], timeout=timeout_s(), max_retries=retries())


def warm_provider():
    """Import the provider runtime before serving questions; performs no model request."""
    if os.environ.get('FLOORWISE_OFFLINE')=='1' or not info().available:return
    instance=client()
    instance.close()
    # These tools have numerical-library imports, but importing them computes no scenario.
    from floorwise.agent import scenarios,insight_tools  # noqa: F401
