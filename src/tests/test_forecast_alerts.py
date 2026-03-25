"""Tests for forecast staleness and API failure alerting."""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.services.forecast_alerts import (
    _send_failure_alert,
    _send_recovery_alert,
    _send_stale_alert,
    check_and_alert,
    check_consecutive_failures,
    check_staleness,
    log_refresh_result,
)


@pytest.fixture
def db_path(tmp_path):
    """Create a temp DB with the required tables."""
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE forecast (
            date TEXT, location TEXT, high REAL, low REAL,
            summary TEXT, description TEXT, last_updated TEXT,
            hourly_json TEXT, timezone TEXT,
            PRIMARY KEY (date, location)
        )
    """)
    conn.execute("""
        CREATE TABLE forecast_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            alert_sent_at TEXT,
            recovery_sent_at TEXT,
            details TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE forecast_refresh_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tier TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            error TEXT
        )
    """)
    conn.commit()
    conn.close()
    return path


def test_log_refresh_success(db_path):
    log_refresh_result(db_path, "tier1", success=True)
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT tier, status, error FROM forecast_refresh_log").fetchone()
    conn.close()
    assert row[0] == "tier1"
    assert row[1] == "success"
    assert row[2] is None


def test_log_refresh_failure(db_path):
    log_refresh_result(db_path, "tier2", success=False, error="400 Bad Request")
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT tier, status, error FROM forecast_refresh_log").fetchone()
    conn.close()
    assert row[1] == "failure"
    assert "400" in row[2]


def test_consecutive_failures_below_threshold(db_path):
    log_refresh_result(db_path, "tier1", success=False, error="err")
    log_refresh_result(db_path, "tier1", success=False, error="err")
    log_refresh_result(db_path, "tier1", success=True)
    is_failing, count, _ = check_consecutive_failures(db_path)
    assert is_failing is False


def test_consecutive_failures_at_threshold(db_path):
    for _ in range(3):
        log_refresh_result(db_path, "tier1", success=False, error="400 Bad Request")
    is_failing, count, last_error = check_consecutive_failures(db_path)
    assert is_failing is True
    assert "400" in last_error


def test_staleness_fresh_data(db_path):
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO forecast (date, location, high, low, last_updated) VALUES (?, ?, ?, ?, ?)",
        ("2026-03-25", "Munich", 15, 5, now),
    )
    conn.commit()
    conn.close()
    is_stale, _, hours = check_staleness(db_path)
    assert is_stale is False
    assert hours < 1


def test_staleness_old_data(db_path):
    old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO forecast (date, location, high, low, last_updated) VALUES (?, ?, ?, ?, ?)",
        ("2026-03-25", "Munich", 15, 5, old),
    )
    conn.commit()
    conn.close()
    is_stale, _, hours = check_staleness(db_path)
    assert is_stale is True
    assert hours >= 4


@patch("src.services.forecast_alerts.send_email")
def test_send_stale_alert_sends_email(mock_send, db_path):
    with patch.dict("os.environ", {"ADMIN_EMAIL": "admin@test.com"}):
        _send_stale_alert(db_path, "2026-03-23T10:00:00", 48.0)
    mock_send.assert_called_once()
    subject = mock_send.call_args[0][1]
    assert "stale" in subject.lower()
    assert "48h" in subject


@patch("src.services.forecast_alerts.send_email")
def test_alert_dedup_within_cooldown(mock_send, db_path):
    with patch.dict("os.environ", {"ADMIN_EMAIL": "admin@test.com", "ALERT_COOLDOWN_HOURS": "6"}):
        _send_stale_alert(db_path, "2026-03-23T10:00:00", 48.0)
        assert mock_send.call_count == 1
        _send_stale_alert(db_path, "2026-03-23T10:00:00", 50.0)
        assert mock_send.call_count == 1  # deduped


@patch("src.services.forecast_alerts.send_email")
def test_send_failure_alert(mock_send, db_path):
    with patch.dict("os.environ", {"ADMIN_EMAIL": "admin@test.com"}):
        _send_failure_alert(db_path, 5, "400 Bad Request")
    mock_send.assert_called_once()
    subject = mock_send.call_args[0][1]
    assert "5 consecutive" in subject


@patch("src.services.forecast_alerts.send_email")
def test_recovery_resolves_active_alerts(mock_send, db_path):
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO forecast_alerts (alert_type, status, created_at, alert_sent_at) "
        "VALUES ('stale_data', 'active', ?, ?)",
        (now, now),
    )
    conn.commit()
    conn.close()

    with patch.dict("os.environ", {"ADMIN_EMAIL": "admin@test.com"}):
        _send_recovery_alert(db_path)

    mock_send.assert_called_once()
    subject = mock_send.call_args[0][1]
    assert "recovered" in subject.lower()

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status, resolved_at FROM forecast_alerts").fetchone()
    conn.close()
    assert row[0] == "resolved"
    assert row[1] is not None


@patch("src.services.forecast_alerts.send_email")
def test_recovery_noop_no_active_alerts(mock_send, db_path):
    with patch.dict("os.environ", {"ADMIN_EMAIL": "admin@test.com"}):
        _send_recovery_alert(db_path)
    mock_send.assert_not_called()


@patch("src.services.forecast_alerts.send_email")
def test_check_and_alert_end_to_end(mock_send, db_path):
    """Failures accumulate -> alert fires -> success -> recovery."""
    # Insert fresh forecast data so staleness doesn't fire
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO forecast (date, location, high, low, last_updated) VALUES (?, ?, ?, ?, ?)",
        ("2026-03-25", "Munich", 15, 5, now),
    )
    conn.commit()
    conn.close()

    with patch.dict("os.environ", {"ADMIN_EMAIL": "admin@test.com"}):
        # 3 failures -> should trigger alert
        for _ in range(3):
            log_refresh_result(db_path, "tier1", success=False, error="400 Bad Request")
        check_and_alert(db_path)
        assert mock_send.call_count == 1  # failure alert

        # Log success, check again -> should trigger recovery
        log_refresh_result(db_path, "tier1", success=True)
        check_and_alert(db_path)
        assert mock_send.call_count == 2  # recovery alert


@patch("src.services.forecast_alerts.send_email")
def test_noop_without_admin_email(mock_send, db_path):
    with patch.dict("os.environ", {}, clear=True):
        os.environ.pop("ADMIN_EMAIL", None)
        for _ in range(3):
            log_refresh_result(db_path, "tier1", success=False, error="err")
        check_and_alert(db_path)
    mock_send.assert_not_called()
