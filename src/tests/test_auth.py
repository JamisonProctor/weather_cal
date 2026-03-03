from datetime import datetime, timedelta, timezone

from jose import jwt

from src.web.auth import ALGORITHM, create_session_token, decode_session_token


def test_create_and_decode_session_token(monkeypatch):
    monkeypatch.setattr("src.web.auth.SECRET_KEY", "test-secret")
    token = create_session_token(42)
    assert decode_session_token(token) == 42


def test_decode_invalid_token_returns_none():
    assert decode_session_token("not-a-valid-jwt-token") is None


def test_decode_expired_token_returns_none(monkeypatch):
    monkeypatch.setattr("src.web.auth.SECRET_KEY", "test-secret")
    expired_token = jwt.encode(
        {"user_id": 1, "exp": datetime.now(timezone.utc) - timedelta(days=1)},
        "test-secret",
        algorithm=ALGORITHM,
    )
    assert decode_session_token(expired_token) is None
