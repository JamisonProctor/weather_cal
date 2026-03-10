import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.services.forecast_store import ForecastStore
from src.web.db import create_feedback_table, create_user_preferences_table
from src.events.db import create_event_tables
from src.integrations.google_push import (
    create_google_tokens_table,
    delete_google_calendar,
    delete_google_tokens,
    get_google_connected_users,
    get_google_credentials,
    google_oauth_enabled,
    is_google_connected,
    store_google_tokens,
    create_weathercal_calendar,
    push_events_for_user,
    refresh_and_persist,
)
from src.web.db import create_user, DEFAULT_PREFS


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    ForecastStore(db_path=path)
    create_feedback_table(path)
    create_user_preferences_table(path)
    create_event_tables(path)
    create_google_tokens_table(path)
    return path


def _make_credentials(token="access_tok", refresh="refresh_tok", expiry=None):
    cred = MagicMock()
    cred.token = token
    cred.refresh_token = refresh
    cred.expiry = expiry or (datetime.now(timezone.utc) + timedelta(hours=1))
    cred.valid = True
    return cred


# --- Table creation ---

def test_create_google_tokens_table_idempotent(db_path):
    create_google_tokens_table(db_path)
    create_google_tokens_table(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='google_tokens'").fetchone()
    conn.close()
    assert row is not None


# --- Store and retrieve ---

def test_store_and_retrieve_tokens(db_path):
    user_id = create_user(db_path, "test@example.com", "supersecretpass1")
    cred = _make_credentials()
    store_google_tokens(db_path, user_id, cred, "cal123@group.calendar.google.com")

    retrieved = get_google_credentials(db_path, user_id)
    assert retrieved is not None
    assert retrieved.token == "access_tok"
    assert retrieved.refresh_token == "refresh_tok"


def test_delete_tokens(db_path):
    user_id = create_user(db_path, "del@example.com", "supersecretpass1")
    cred = _make_credentials()
    store_google_tokens(db_path, user_id, cred, "cal123")

    delete_google_tokens(db_path, user_id)
    assert get_google_credentials(db_path, user_id) is None


def test_is_google_connected_true(db_path):
    user_id = create_user(db_path, "conn@example.com", "supersecretpass1")
    cred = _make_credentials()
    store_google_tokens(db_path, user_id, cred, "cal123")
    assert is_google_connected(db_path, user_id) is True


def test_is_google_connected_false(db_path):
    user_id = create_user(db_path, "noconn@example.com", "supersecretpass1")
    assert is_google_connected(db_path, user_id) is False


def test_get_google_connected_users_filters_revoked(db_path):
    user1 = create_user(db_path, "active@example.com", "supersecretpass1")
    user2 = create_user(db_path, "revoked@example.com", "supersecretpass1")
    cred = _make_credentials()
    store_google_tokens(db_path, user1, cred, "cal1")
    store_google_tokens(db_path, user2, cred, "cal2")

    # Mark user2 as revoked
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE google_tokens SET status = 'revoked' WHERE user_id = ?", (user2,))
    conn.commit()
    conn.close()

    connected = get_google_connected_users(db_path)
    user_ids = [u["user_id"] for u in connected]
    assert user1 in user_ids
    assert user2 not in user_ids


# --- google_oauth_enabled ---

def test_google_oauth_enabled_when_set(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    assert google_oauth_enabled() is True


def test_google_oauth_enabled_when_not_set(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    assert google_oauth_enabled() is False


# --- Refresh / revoke ---

def test_push_events_marks_revoked_on_refresh_error(db_path):
    from google.auth.exceptions import RefreshError

    user_id = create_user(db_path, "revoke@example.com", "supersecretpass1")
    cred = _make_credentials()
    store_google_tokens(db_path, user_id, cred, "cal123")

    # Make credentials expired so refresh is attempted
    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.refresh.side_effect = RefreshError("revoked")

    with patch("src.integrations.google_push.get_google_credentials", return_value=mock_creds):
        push_events_for_user(db_path, user_id, [], DEFAULT_PREFS, "Munich", "Europe/Berlin")

    # After RefreshError, should be marked revoked
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status FROM google_tokens WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    assert row[0] == "revoked"


def test_create_weathercal_calendar():
    mock_service = MagicMock()
    mock_service.calendars().insert().execute.return_value = {"id": "new_cal_id"}
    result = create_weathercal_calendar(mock_service)
    assert result == "new_cal_id"


def test_delete_google_calendar_calls_api(db_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    user_id = create_user(db_path, "delcal@example.com", "supersecretpass1")
    cred = _make_credentials()
    store_google_tokens(db_path, user_id, cred, "cal_to_delete@group.calendar.google.com")

    mock_service = MagicMock()
    with patch("src.integrations.google_push.refresh_and_persist", return_value=cred), \
         patch("src.integrations.google_push.build_google_service", return_value=mock_service):
        delete_google_calendar(db_path, user_id)

    mock_service.calendars().delete.assert_called_with(calendarId="cal_to_delete@group.calendar.google.com")


def test_delete_google_calendar_handles_404(db_path, monkeypatch):
    """If the calendar was already deleted by the user, don't raise."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    user_id = create_user(db_path, "delcal404@example.com", "supersecretpass1")
    cred = _make_credentials()
    store_google_tokens(db_path, user_id, cred, "gone_cal@group.calendar.google.com")

    mock_service = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status = 404
    from googleapiclient.errors import HttpError
    mock_service.calendars().delete().execute.side_effect = HttpError(mock_resp, b"Not Found")

    with patch("src.integrations.google_push.refresh_and_persist", return_value=cred), \
         patch("src.integrations.google_push.build_google_service", return_value=mock_service):
        delete_google_calendar(db_path, user_id)  # should not raise
