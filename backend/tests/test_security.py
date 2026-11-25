
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings
from app.core.security import (
    JWT_ALGORITHM,
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)


def test_password_hash_and_verify():

    hashed = hash_password("TestPassword123")

    assert hashed != "TestPassword123"

    assert verify_password(
        "TestPassword123",
        hashed,
    )

    assert not verify_password(
        "WrongPassword",
        hashed,
    )


def test_invalid_password_hash():

    assert not verify_password(
        "123456",
        "invalid-hash",
    )


def test_create_and_decode_access_token():

    token = create_access_token(5)

    payload = decode_access_token(token)

    assert payload is not None

    assert payload["sub"] == "5"

    assert "iat" in payload
    assert "exp" in payload


def test_empty_token():

    assert decode_access_token("") is None


def test_expired_token():

    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": "5",
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )

    assert decode_access_token(token) is None


def test_tampered_token():

    token = create_access_token(5)

    tampered_token = (
        token[:-1]
        + ("a" if token[-1] != "a" else "b")
    )

    assert decode_access_token(tampered_token) is None
