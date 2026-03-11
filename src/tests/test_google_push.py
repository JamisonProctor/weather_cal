import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.integrations.google_push import (
    _cleanup_stale_events,
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


# --- Stale event cleanup ---

class TestCleanupStaleEvents:
    """Tests for _cleanup_stale_events."""

    def _mock_service(self, existing_items):
        service = MagicMock()
        service.events().list().execute.return_value = {"items": existing_items}
        return service

    def test_deletes_stale_timed_events(self):
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Berlin")
        stale_event = {
            "id": "evt_stale",
            "iCalUID": "stale_uid@weathercal.app",
            "start": {"dateTime": "2026-03-11T08:00:00+01:00"},
        }
        service = self._mock_service([stale_event])

        _cleanup_stale_events(service, "cal123", "2026-03-11",
                              expected_allday_uids=set(),
                              expected_timed_uids={"current_uid@weathercal.app"},
                              tz=tz)

        service.events().delete.assert_called_with(calendarId="cal123", eventId="evt_stale")

    def test_preserves_current_timed_events(self):
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Berlin")
        current_uid = "current_uid@weathercal.app"
        current_event = {
            "id": "evt_current",
            "iCalUID": current_uid,
            "start": {"dateTime": "2026-03-11T08:00:00+01:00"},
        }
        service = self._mock_service([current_event])

        _cleanup_stale_events(service, "cal123", "2026-03-11",
                              expected_allday_uids=set(),
                              expected_timed_uids={current_uid},
                              tz=tz)

        service.events().delete.assert_not_called()

    def test_deletes_allday_when_disabled(self):
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Berlin")
        allday_event = {
            "id": "evt_allday",
            "iCalUID": "allday_uid@weathercal.app",
            "start": {"date": "2026-03-11"},
        }
        service = self._mock_service([allday_event])

        # Empty expected_allday_uids = all-day events disabled
        _cleanup_stale_events(service, "cal123", "2026-03-11",
                              expected_allday_uids=set(),
                              expected_timed_uids=set(),
                              tz=tz)

        service.events().delete.assert_called_with(calendarId="cal123", eventId="evt_allday")

    def test_preserves_allday_when_enabled(self):
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Berlin")
        allday_uid = "allday_uid@weathercal.app"
        allday_event = {
            "id": "evt_allday",
            "iCalUID": allday_uid,
            "start": {"date": "2026-03-11"},
        }
        service = self._mock_service([allday_event])

        _cleanup_stale_events(service, "cal123", "2026-03-11",
                              expected_allday_uids={allday_uid},
                              expected_timed_uids=set(),
                              tz=tz)

        service.events().delete.assert_not_called()

    def test_handles_list_api_error(self):
        from googleapiclient.errors import HttpError
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Berlin")

        service = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status = 500
        service.events().list().execute.side_effect = HttpError(mock_resp, b"Server Error")

        # Should not raise
        _cleanup_stale_events(service, "cal123", "2026-03-11",
                              expected_allday_uids=set(),
                              expected_timed_uids=set(),
                              tz=tz)
