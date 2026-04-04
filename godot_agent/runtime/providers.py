from __future__ import annotations

from dataclasses import dataclass


REASONING_EFFORT_LEVELS = ("auto", "minimal", "low", "medium", "high", "xhigh")


@dataclass(frozen=True)
class ProviderPreset:
    provider: str
    name: str
    base_url: str
    model: str
    key_url: str = ""
    key_prefix: str = ""


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "openai": ProviderPreset(
        provider="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        model="gpt-5.4",
        key_url="https://platform.openai.com/api-keys",
        key_prefix="sk-",
    ),
    "anthropic": ProviderPreset(
        provider="anthropic",
        name="Anthropic",
        base_url="https://api.anthropic.com/v1",
        model="claude-sonnet-4.6",
        key_url="https://console.anthropic.com/settings/keys",
        key_prefix="sk-ant-",
    ),
    "openrouter": ProviderPreset(
        provider="openrouter",
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        model="openai/gpt-5.4",
        key_url="https://openrouter.ai/keys",
        key_prefix="sk-or-",
    ),
    "gemini": ProviderPreset(
        provider="gemini",
        name="Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model="gemini-3.1-pro",
        key_url="https://aistudio.google.com/apikey",
    ),
    "xai": ProviderPreset(
        provider="xai",
        name="xAI",
        base_url="https://api.x.ai/v1",
        model="grok-4",
        key_url="https://console.x.ai",
    ),
    "glm": ProviderPreset(
        provider="glm",
        name="Z.AI / GLM",
        base_url="https://api.z.ai/api/paas/v4",
        model="glm-5",
        key_url="https://z.ai",
    ),
    "minimax": ProviderPreset(
        provider="minimax",
        name="MiniMax",
        base_url="https://api.minimax.io/v1",
        model="MiniMax-M2.5",
        key_url="https://platform.minimax.io",
    ),
    "custom": ProviderPreset(
        provider="custom",
        name="Custom",
        base_url="",
        model="",
    ),
}


def normalize_provider(provider: str | None) -> str:
    value = (provider or "").strip().lower()
    if not value:
        return "openai"
    aliases = {
        "claude": "anthropic",
        "anthropic": "anthropic",
        "google": "gemini",
        "gemini": "gemini",
        "xai": "xai",
        "grok": "xai",
        "zai": "glm",
        "zhipu": "glm",
        "glm": "glm",
        "minimax": "minimax",
        "openai": "openai",
        "openrouter": "openrouter",
        "custom": "custom",
    }
    return aliases.get(value, value)


def infer_provider(base_url: str = "", model: str = "", provider: str | None = None) -> str:
    explicit = normalize_provider(provider)
    if explicit not in {"openai", ""}:
        return explicit

    base = (base_url or "").lower()
    model_lower = (model or "").lower()

    if "anthropic.com" in base or model_lower.startswith("claude-"):
        return "anthropic"
    if "openrouter.ai" in base:
        return "openrouter"
    if "generativelanguage.googleapis.com" in base or model_lower.startswith("gemini-"):
        return "gemini"
    if ".x.ai" in base or model_lower.startswith("grok-"):
        return "xai"
    if "minimax" in base or model_lower.startswith("minimax-"):
        return "minimax"
    if "z.ai" in base or "bigmodel" in base or model_lower.startswith("glm-"):
        return "glm"
    return "openai"


def chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def canonical_model_name(model: str) -> str:
    lowered = model.lower().strip()
    if "/" in lowered:
        lowered = lowered.split("/", 1)[1]
    return lowered


def uses_max_completion_tokens(provider: str, model: str) -> bool:
    provider = normalize_provider(provider)
    canonical = canonical_model_name(model)
    return provider in {"openai", "openrouter"} and canonical.startswith("gpt-5")


def should_send_reasoning_effort(provider: str, model: str, effort: str) -> bool:
    provider = normalize_provider(provider)
    effort = (effort or "").strip().lower()
    if not effort or effort == "auto":
        return False
    canonical = canonical_model_name(model)
    if provider == "xai" and canonical.startswith("grok-4"):
        return False
    return provider in {"openai", "gemini"}


def supports_computer_use(provider: str, model: str) -> bool:
    provider = normalize_provider(provider)
    canonical = canonical_model_name(model)
    return provider == "openai" and canonical.startswith("gpt-5.4")


def anthropic_thinking_budget(effort: str) -> int | None:
    effort = (effort or "").strip().lower()
    return {
        "minimal": 1024,
        "low": 1024,
        "medium": 2048,
        "high": 4096,
        "xhigh": 8192,
    }.get(effort)
