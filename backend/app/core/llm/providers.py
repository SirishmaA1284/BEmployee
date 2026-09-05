"""Provider factory (docs/decisions.md ADR-005).

Selection is configuration-only: `LLM_PROVIDER` env var decides which
provider `get_llm_provider()` returns, so swapping models never touches
agent code. The mock provider is the fallback default so the app runs with
no API key configured.
"""

from app.core.config import get_settings
from app.core.llm.base import LLMProvider
from app.core.llm.mock import MockProvider
from app.core.llm.openai import OpenAIProvider


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    provider_name = settings.llm_provider.strip().lower()

    if provider_name == "openai":
        if not settings.openai_api_key:
            # No key configured (fresh clone, local demo) — fall back to the
            # deterministic mock so the app never crashes on startup or chat.
            return MockProvider()
        return OpenAIProvider()
    if provider_name in ("anthropic", "gemini"):
        raise NotImplementedError(
            f"LLM provider '{provider_name}' is stubbed but not implemented "
            "(docs/decisions.md ADR-005) — set LLM_PROVIDER=mock or openai"
        )
    if provider_name in ("mock", ""):
        return MockProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {provider_name}")