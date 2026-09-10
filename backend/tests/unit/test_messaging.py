"""Unit tests for real Telegram/WhatsApp delivery (app/services/messaging.py).

The senders make real HTTP calls; these tests replace httpx with a fake
client so we assert the exact URL, headers, and body without a network.
"""

from app.core.config import get_settings
from app.services import messaging
import pytest


def _set_settings(monkeypatch, **overrides):
    settings = get_settings()
    for field, value in overrides.items():
        monkeypatch.setattr(settings, field, value)
    return settings


class FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self) -> dict:
        return self._json


class FakeClient:
    """Records every call; returns a configurable response."""

    calls: list[tuple[str, dict]] = []
    response: FakeResponse = FakeResponse(200, {"ok": True})

    def __init__(self, *args, **kwargs) -> None:
        self.calls = FakeClient.calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def post(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append((url, kwargs))
        return self.response


@pytest.fixture(autouse=True)
def _reset_fake_client():
    """Each test starts with a clean call log and a default 200 response."""
    FakeClient.calls = []
    FakeClient.response = FakeResponse(200, {"ok": True})
    yield


def test_telegram_configured_requires_token_and_chat_id(monkeypatch):
    _set_settings(monkeypatch, telegram_bot_token="", telegram_chat_id="")
    assert messaging.telegram_configured() is False

    _set_settings(monkeypatch, telegram_bot_token="123:abc", telegram_chat_id="")
    assert messaging.telegram_configured() is False

    _set_settings(monkeypatch, telegram_bot_token="123:abc", telegram_chat_id="42")
    assert messaging.telegram_configured() is True


def test_whatsapp_configured_requires_all_three(monkeypatch):
    _set_settings(
        monkeypatch,
        whatsapp_access_token="",
        whatsapp_phone_number_id="",
        whatsapp_to_phone="",
    )
    assert messaging.whatsapp_configured() is False

    _set_settings(
        monkeypatch,
        whatsapp_access_token="tok",
        whatsapp_phone_number_id="1234",
        whatsapp_to_phone="",
    )
    assert messaging.whatsapp_configured() is False

    _set_settings(
        monkeypatch,
        whatsapp_access_token="tok",
        whatsapp_phone_number_id="1234",
        whatsapp_to_phone="+919800000000",
    )
    assert messaging.whatsapp_configured() is True


async def test_send_telegram_unconfigured_returns_error_without_network(monkeypatch):
    _set_settings(monkeypatch, telegram_bot_token="", telegram_chat_id="")
    result = await messaging.send_telegram_message("hello")
    assert result == {"ok": False, "provider": "telegram", "error": "telegram not configured"}


async def test_send_telegram_posts_correct_url_and_body(monkeypatch):
    _set_settings(monkeypatch, telegram_bot_token="123:abc", telegram_chat_id="42")
    FakeClient.response = FakeResponse(200, {"ok": True, "result": {"message_id": 7}})
    monkeypatch.setattr(messaging.httpx, "AsyncClient", FakeClient)

    result = await messaging.send_telegram_message("Low stock alert")

    assert result["ok"] is True
    assert result["message_id"] == 7
    assert len(FakeClient.calls) == 1
    url, kwargs = FakeClient.calls[0]
    assert url == "https://api.telegram.org/bot123:abc/sendMessage"
    assert kwargs["json"] == {"chat_id": "42", "text": "Low stock alert"}


async def test_send_telegram_http_error_is_captured(monkeypatch):
    _set_settings(monkeypatch, telegram_bot_token="123:abc", telegram_chat_id="42")
    FakeClient.response = FakeResponse(400, {}, text="Bad Request: chat not found")
    monkeypatch.setattr(messaging.httpx, "AsyncClient", FakeClient)

    result = await messaging.send_telegram_message("hello")

    assert result["ok"] is False
    assert "400" in result["error"]


async def test_send_telegram_network_error_is_captured(monkeypatch):
    _set_settings(monkeypatch, telegram_bot_token="123:abc", telegram_chat_id="42")

    class ExplodingClient(FakeClient):
        async def post(self, url, **kwargs):
            raise TimeoutError("boom")

    monkeypatch.setattr(messaging.httpx, "AsyncClient", ExplodingClient)

    result = await messaging.send_telegram_message("hello")

    assert result["ok"] is False
    assert "boom" in result["error"]


async def test_send_whatsapp_posts_correct_url_headers_and_body(monkeypatch):
    _set_settings(
        monkeypatch,
        whatsapp_access_token="secret-token",
        whatsapp_phone_number_id="12345",
        whatsapp_to_phone="+919800000000",
    )
    FakeClient.response = FakeResponse(
        200, {"messages": [{"id": "wamid.ABC123"}]}
    )
    monkeypatch.setattr(messaging.httpx, "AsyncClient", FakeClient)

    result = await messaging.send_whatsapp_message("Stockout: Milk")

    assert result["ok"] is True
    assert result["message_id"] == "wamid.ABC123"
    assert len(FakeClient.calls) == 1
    url, kwargs = FakeClient.calls[0]
    assert url == "https://graph.facebook.com/v21.0/12345/messages"
    assert kwargs["headers"]["Authorization"] == "Bearer secret-token"
    assert kwargs["json"] == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "+919800000000",
        "type": "text",
        "text": {"body": "Stockout: Milk"},
    }


async def test_send_whatsapp_api_error_extracts_detail(monkeypatch):
    _set_settings(
        monkeypatch,
        whatsapp_access_token="secret-token",
        whatsapp_phone_number_id="12345",
        whatsapp_to_phone="+919800000000",
    )
    FakeClient.response = FakeResponse(
        400, {"error": {"message": "Unsupported message type"}}
    )
    monkeypatch.setattr(messaging.httpx, "AsyncClient", FakeClient)

    result = await messaging.send_whatsapp_message("hello")

    assert result["ok"] is False
    assert "Unsupported message type" in result["error"]