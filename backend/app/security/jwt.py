import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import get_settings

settings = get_settings()


class TokenError(Exception):
    """Raised for any invalid/expired/malformed JWT. Callers should treat this
    uniformly as 401 Unauthorized — never leak whether it was expiry vs.
    tampering vs. malformed, which would help an attacker.
    """


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
