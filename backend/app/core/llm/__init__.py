"""LLM provider abstraction (docs/decisions.md ADR-005).

The rest of the application depends only on the `LLMProvider` interface in
`base.py`. Providers are selected through `get_llm_provider()`; the Mock
provider is the default so the app (and every test) runs without API keys.
"""

from app.core.llm.base import LLMProvider, LLMResponse, ToolCallRequest, ToolCallResult
from app.core.llm.providers import get_llm_provider

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "ToolCallRequest",
    "ToolCallResult",
    "get_llm_provider",
]