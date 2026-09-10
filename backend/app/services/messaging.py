"""Real WhatsApp + Telegram delivery for notifications.

The notification service (docs/decisions.md A6) always writes the IN_APP row;
when the corresponding credentials are configured it dispatches the message to
the real providers here. Everything in this module is best-effort: a failed
delivery never raises into the caller — it returns `{"ok": False, "error": ...}`
so the notification row still records the attempt and the app keeps working.

Telegram: Bot API `sendMessage` (https://core.telegram.org/bots/api).
WhatsApp: Meta Business Cloud API `/messages` with a text body. Note the
platform only lets businesses start conversations with approved *templates*;
plain text bodies are delivered inside the 24h customer-service window (a
reply). Template sending is out of MVP scope — see docs/security.md A6 notes.

If credentials are missing, the caller falls back to the MOCK_* rows and no
network call is made.
"""

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
WHATSAPP_API = "https://graph.facebook.com/v21.0/{phone_number_id}/messages"
_REQUEST_TIMEOUT_SECONDS = 10.0


def telegram_configured() -> bool:
    settings = get_settings()
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def whatsapp_configured() -> bool:
    settings = get_settings()
    return bool(
        settings.whatsapp_access_token
        and settings.whatsapp_phone_number_id
        and settings.whatsapp_to_phone
    )


def _delivery_text(title: str, message: str) -> str:
    return f"{title}\n{message}"


async def send_telegram_message(
    text: str, *, token: str | None = None, chat_id: str | None = None
) -> dict:
    """Send `text` to the configured Telegram chat. Returns
    `{"ok": bool, "provider": "telegram", ...}` — never raises.
    """
    settings = get_settings()
    token = token or settings.telegram_bot_token
    chat_id = chat_id or settings.telegram_chat_id
    if not token or not chat_id:
        return {"ok": False, "provider": "telegram", "error": "telegram not configured"}
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                TELEGRAM_API.format(token=token),
                json={"chat_id": chat_id, "text": text},
            )
        if response.status_code == 200:
            data = response.json()
            return {
                "ok": True,
                "provider": "telegram",
                "message_id": (data.get("result") or {}).get("message_id"),
            }
        return {
            "ok": False,
            "provider": "telegram",
            "error": f"telegram HTTP {response.status_code}: {response.text[:200]}",
        }
    except Exception as exc:  # network errors, timeouts, bad responses
        logger.warning("telegram delivery failed: %s", exc)
        return {"ok": False, "provider": "telegram", "error": str(exc)}


async def send_whatsapp_message(
    text: str,
    *,
    access_token: str | None = None,
    phone_number_id: str | None = None,
    to_phone: str | None = None,
) -> dict:
    """Send `text` to the configured WhatsApp number via the Meta Cloud API.
    Returns `{"ok": bool, "provider": "whatsapp", ...}` — never raises.
    """
    settings = get_settings()
    access_token = access_token or settings.whatsapp_access_token
    phone_number_id = phone_number_id or settings.whatsapp_phone_number_id
    to_phone = to_phone or settings.whatsapp_to_phone
    if not access_token or not phone_number_id or not to_phone:
        return {"ok": False, "provider": "whatsapp", "error": "whatsapp not configured"}
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                WHATSAPP_API.format(phone_number_id=phone_number_id),
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to_phone,
                    "type": "text",
                    "text": {"body": text},
                },
            )
        if response.status_code == 200 or response.status_code == 201:
            data = response.json()
            return {
                "ok": True,
                "provider": "whatsapp",
                "message_id": (data.get("messages") or [{}])[0].get("id"),
            }
        detail = (response.json().get("error") or {}).get("message") or response.text[:200]
        return {
            "ok": False,
            "provider": "whatsapp",
            "error": f"whatsapp HTTP {response.status_code}: {detail}",
        }
    except Exception as exc:  # network errors, timeouts, bad responses
        logger.warning("whatsapp delivery failed: %s", exc)
        return {"ok": False, "provider": "whatsapp", "error": str(exc)}