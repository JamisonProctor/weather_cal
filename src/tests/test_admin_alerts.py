import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.integrations.google_push import (
    _clear_calendar_id,
    _mark_revoked,
    create_google_tokens_table,
    store_google_tokens,
)
from src.services.admin_alerts import send_google_alert
from src.web.db import create_user


def _make_credentials(token="access_tok", refresh="refresh_tok", expiry=None):
    cred = MagicMock()
    cred.token = token
    cred.refresh_token = refresh
    cred.expiry = expiry or (datetime.now(timezone.utc) + timedelta(hours=1))
    cred.valid = True
    return cred


def _setup_user_with_tokens(db_path):
    """Create a user with active Google tokens. Returns user_id."""
    user_id = create_user(db_path, "oauth@example.com", "supersecretpass1")
    cred = _make_credentials()
    store_google_tokens(db_path, user_id, cred, "cal123@group.calendar.google.com")
    return user_id


# --- send_google_alert ---

@patch("src.services.admin_alerts.send_email")
def test_sends_email_on_revocation(mock_send, db_path, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    user_id = _setup_user_with_tokens(db_path)

    send_google_alert(db_path, user_id, "revoked")

    mock_send.assert_called_once()
    args = mock_send.call_args
    assert args[0][0] == "admin@example.com"
    assert "revoked" in args[0][1]
    assert "oauth@example.com" in args[0][1]


@patch("src.services.admin_alerts.send_email")
def test_noop_without_admin_email(mock_send, db_path, monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    user_id = _setup_user_with_tokens(db_path)

    send_google_alert(db_path, user_id, "revoked")

    mock_send.assert_not_called()


@patch("src.services.admin_alerts.send_email")
def test_dedup_skips_second_alert(mock_send, db_path, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    user_id = _setup_user_with_tokens(db_path)

    send_google_alert(db_path, user_id, "revoked")
    send_google_alert(db_path, user_id, "revoked")

    assert mock_send.call_count == 1


@patch("src.services.admin_alerts.send_email")
def test_reconnect_resets_alert(mock_send, db_path, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    user_id = _setup_user_with_tokens(db_path)

    # First failure cycle
    send_google_alert(db_path, user_id, "revoked")
    assert mock_send.call_count == 1

    # Reconnect resets alert_sent_at
    cred = _make_credentials()
    store_google_tokens(db_path, user_id, cred, "cal456@group.calendar.google.com")

    # Second failure cycle
    send_google_alert(db_path, user_id, "revoked")
    assert mock_send.call_count == 2


@patch("src.services.admin_alerts.send_email", side_effect=Exception("SMTP down"))
def test_alert_failure_does_not_propagate(mock_send, db_path, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
    user_id = _setup_user_with_tokens(db_path)

    # Should not raise
    send_google_alert(db_path, user_id, "revoked")


# --- Integration: _mark_revoked triggers alert ---

@patch("src.integrations.google_push.send_google_alert")
def test_mark_revoked_triggers_alert(mock_alert, db_path):
    user_id = _setup_user_with_tokens(db_path)

    _mark_revoked(db_path, user_id)

    mock_alert.assert_called_once_with(db_path, user_id, "revoked")


@patch("src.integrations.google_push.send_google_alert")
def test_clear_calendar_id_triggers_alert(mock_alert, db_path):
    user_id = _setup_user_with_tokens(db_path)

    _clear_calendar_id(db_path, user_id)

    mock_alert.assert_called_once_with(db_path, user_id, "calendar_deleted")
