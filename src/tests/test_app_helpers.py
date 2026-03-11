"""Tests for app.py helper functions: _require_login, _convert_thresholds_to_celsius."""
from unittest.mock import MagicMock

import pytest

from src.web.app import _convert_thresholds_to_celsius, _require_login, _LoginRequired


def test_require_login_returns_user_id(auth_cookies):
    """_require_login returns user_id when session cookie is valid."""
    user_id, cookies = auth_cookies()
    request = MagicMock()
    request.cookies = cookies
    result = _require_login(request)
    assert result == user_id


def test_require_login_raises_without_session():
    """_require_login raises _LoginRequired when no session cookie."""
    request = MagicMock()
    request.cookies = {}
    with pytest.raises(_LoginRequired):
        _require_login(request)


def test_require_login_raises_with_invalid_session():
    """_require_login raises _LoginRequired with an invalid session token."""
    request = MagicMock()
    request.cookies = {"session": "bogus-token"}
    with pytest.raises(_LoginRequired):
        _require_login(request)


def test_convert_thresholds_to_celsius_freezing():
    """32°F should convert to 0°C."""
    cold, warm, hot = _convert_thresholds_to_celsius(32.0, 57.2, 82.4)
    assert abs(cold - 0.0) < 0.01
    assert abs(warm - 14.0) < 0.01
    assert abs(hot - 28.0) < 0.01


def test_convert_thresholds_to_celsius_known_values():
    """Test with the default F equivalents of the default C thresholds."""
    cold, warm, hot = _convert_thresholds_to_celsius(37.4, 57.2, 82.4)
    assert abs(cold - 3.0) < 0.01
    assert abs(warm - 14.0) < 0.01
    assert abs(hot - 28.0) < 0.01
