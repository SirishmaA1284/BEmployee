import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

from app.core.config import get_settings
from app.security.jwt import TokenError, create_access_token, decode_access_token

settings = get_settings()


def test_create_and_decode_round_trip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)


def test_decode_rejects_garbage_token():
    with pytest.raises(TokenError):
        decode_access_token("not.a.valid.jwt")


def test_decode_rejects_expired_token():
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": str(user_id),
        "iat": now - timedelta(minutes=120),
        "exp": now - timedelta(minutes=60),
    }
    expired_token = pyjwt.encode(
        expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )
    with pytest.raises(TokenError):
        decode_access_token(expired_token)


def test_decode_rejects_token_signed_with_wrong_secret():
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=60)}
    forged_token = pyjwt.encode(payload, "a completely different secret", algorithm=settings.jwt_algorithm)
    with pytest.raises(TokenError):
        decode_access_token(forged_token)
