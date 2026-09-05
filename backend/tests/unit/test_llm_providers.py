"""MockProvider and provider factory tests (docs/decisions.md ADR-005)."""

import pytest

from app.core.config import get_settings
from app.core.llm.base import LLMResponse, ToolCallRequest, ToolCallResult
from app.core.llm.mock import MockProvider, _keyword_arguments, _parse_items
from app.core.llm.providers import get_llm_provider

SAMPLE_TOOL = ToolCallRequest(
    name="classify_intent",
    description="Classify the request.",
    input_schema={"type": "object", "properties": {"intent": {"type": "string"}}},
)


@pytest.mark.asyncio
async def test_mock_provider_returns_scripted_tool_call_in_order():
    provider = MockProvider(
        script=[
            {"tool": "search_customers", "arguments": {"query": "Rahul"}},
            {"tool": "search_products", "arguments": {"query": "coffee"}},
            {"content": "done"},
        ]
    )
    first = await provider.generate(system="", messages=[{"role": "user", "content": "hi"}], tools=[SAMPLE_TOOL])
    assert first.tool_calls[0].name == "search_customers"
    assert first.tool_calls[0].arguments == {"query": "Rahul"}

    second = await provider.generate(system="", messages=[{"role": "user", "content": "hi"}], tools=[SAMPLE_TOOL])
    assert second.tool_calls[0].name == "search_products"

    third = await provider.generate(system="", messages=[{"role": "user", "content": "hi"}], tools=[SAMPLE_TOOL])
    assert third.content == "done"
    assert third.tool_calls == []


@pytest.mark.asyncio
async def test_mock_provider_after_script_uses_keyword_rules():
    provider = MockProvider(script=[{"content": "hi"}])
    response = await provider.generate(system="", messages=[{"role": "user", "content": "hi"}], tools=[SAMPLE_TOOL])
    assert response.content == "hi"
    # Script exhausted -> keyword classification kicks in.
    next_response = await provider.generate(
        system="", messages=[{"role": "user", "content": "Which products are running low?"}], tools=[SAMPLE_TOOL]
    )
    assert next_response.tool_calls[0].arguments["intent"] == "LOW_STOCK"


@pytest.mark.asyncio
async def test_mock_provider_no_tools_returns_help_text():
    provider = MockProvider()
    response = await provider.generate(system="", messages=[{"role": "user", "content": "hello"}])
    assert "I can help with" in response.content


def test_keyword_intent_rules():
    cases = {
        "Create an order for Rahul with 3 coffee packets": "CREATE_ORDER",
        "check stock for coffee": "CHECK_INVENTORY",
        "Which products are running low?": "LOW_STOCK",
        "Which supplier gives the best price for coffee?": "COMPARE_SUPPLIERS",
        "Prepare a purchase order for everything likely to run out within 7 days": "CREATE_PURCHASE_ORDER",
        "search for products containing coffee": "SEARCH_PRODUCTS",
        "find customer Rahul": "SEARCH_CUSTOMERS",
        "give me a sales report": "SALES_REPORT",
        "what is the weather": "UNKNOWN",
    }
    for message, expected in cases.items():
        assert _keyword_arguments("classify_intent", message)["intent"] == expected, message


def test_extract_order_parses_customer_and_items():
    arguments = _keyword_arguments(
        "extract_order", "Create an order for Rahul containing 3 coffee packets and 2 sugar bags."
    )
    assert arguments == {
        "customer_query": "Rahul",
        "items": [
            {"product_query": "coffee", "quantity": 3},
            {"product_query": "sugar", "quantity": 2},
        ],
    }


def test_extract_order_without_items_returns_none():
    assert _keyword_arguments("extract_order", "create an order for Rahul") is None


def test_parse_items_rejects_non_product_phrases():
    assert _parse_items("just say hi") is None
    assert _parse_items("reorder everything that is low") is None


def test_extract_product_query():
    assert _keyword_arguments("extract_product_query", "best price for coffee?") == {"query": "coffee"}


def _fresh_settings(monkeypatch, provider: str):
    """get_settings is lru_cached and may already hold .env values; clear it
    so a monkeypatched env var actually takes effect.
    """
    monkeypatch.setenv("LLM_PROVIDER", provider)
    get_settings.cache_clear()


def test_factory_selects_mock_by_default(monkeypatch):
    _fresh_settings(monkeypatch, "mock")
    assert get_llm_provider().name == "mock"


def test_factory_falls_back_to_mock_when_openai_has_no_key(monkeypatch):
    _fresh_settings(monkeypatch, "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert get_llm_provider().name == "mock"


def test_factory_rejects_unknown_provider(monkeypatch):
    _fresh_settings(monkeypatch, "not-a-provider")
    with pytest.raises(ValueError):
        get_llm_provider()


def test_factory_stubs_anthropic_and_gemini(monkeypatch):
    for name in ("anthropic", "gemini"):
        _fresh_settings(monkeypatch, name)
        with pytest.raises(NotImplementedError):
            get_llm_provider()