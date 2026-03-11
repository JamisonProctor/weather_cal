"""Tests for functions extracted during the long-function refactor (commit 4)."""
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from src.constants import DEFAULT_PREFS
from src.web.db import (
    _export_account,
    _export_google_connection,
    _export_poll_logs,
    _get_per_user_stats,
    _get_summary_stats,
    create_feed_token,
    create_user,
    export_user_data,
    get_admin_stats,
    set_user_location,
    upsert_user_preferences,
)
from src.integrations.google_push import _get_valid_credentials


# --- export helpers ---

def test_export_account_returns_user_info(db_path):
    user_id = create_user(db_path, "export@test.com", "supersecretpass1")
    from src.utils.db import get_connection
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        result = _export_account(cur, user_id)
        assert result["email"] == "export@test.com"
        assert "created_at" in result
    finally:
        conn.close()


def test_export_account_missing_user(db_path):
    from src.utils.db import get_connection
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        result = _export_account(cur, 99999)
        assert result == {}
    finally:
        conn.close()


def test_export_poll_logs_empty(db_path):
    user_id = create_user(db_path, "polltest@test.com", "supersecretpass1")
    from src.utils.db import get_connection
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        result = _export_poll_logs(cur, user_id)
        assert result == []
    finally:
        conn.close()


def test_export_google_connection_no_table(db_path):
    """Should return None if google_tokens table doesn't exist."""
    from src.utils.db import get_connection
    conn = get_connection(db_path)
    try:
        # Drop google_tokens if it exists (it was created by conftest)
        conn.execute("DROP TABLE IF EXISTS google_tokens")
        conn.commit()
        cur = conn.cursor()
        result = _export_google_connection(cur, 1)
        assert result is None
    finally:
        conn.close()


# --- admin stats helpers ---

def test_get_summary_stats(db_path):
    user_id = create_user(db_path, "admin@test.com", "supersecretpass1")
    set_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
    create_feed_token(db_path, user_id)
    from src.utils.db import get_connection
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        result = _get_summary_stats(cur)
        assert result["total_users"] >= 1
        assert result["unique_locations"] >= 1
        assert "total_polls" in result
    finally:
        conn.close()


def test_get_per_user_stats(db_path):
    user_id = create_user(db_path, "peruser@test.com", "supersecretpass1")
    set_user_location(db_path, user_id, "Berlin, Germany", 52.52, 13.405, "Europe/Berlin")
    create_feed_token(db_path, user_id)
    upsert_user_preferences(db_path, user_id, **DEFAULT_PREFS)
    from datetime import datetime
    from src.utils.db import get_connection
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        users = _get_per_user_stats(cur, datetime.now())
        assert len(users) >= 1
        user = next(u for u in users if u["email"] == "peruser@test.com")
        assert user["location"] == "Berlin, Germany"
        assert "calendar_app" in user
    finally:
        conn.close()


# --- _get_valid_credentials ---

def test_get_valid_credentials_no_tokens(db_path):
    """Should return (None, None) when user has no Google tokens."""
    user_id = create_user(db_path, "nocreds@test.com", "supersecretpass1")
    creds, cal_id = _get_valid_credentials(db_path, user_id)
    assert creds is None
    assert cal_id is None
