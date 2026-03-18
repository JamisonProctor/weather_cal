"""Tests for src.constants and src.utils.db."""
import sqlite3
import tempfile
import os

from src.constants import (
    COLD_TEMP_THRESHOLD,
    DEFAULT_PREFS,
    HOT_TEMP_THRESHOLD,
    RAIN_MM_THRESHOLD,
    WARM_TEMP_THRESHOLD,
)
from src.utils.db import get_connection


def test_get_connection_returns_connection():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        conn = get_connection(db_path)
        try:
            assert isinstance(conn, sqlite3.Connection)
        finally:
            conn.close()


def test_get_connection_sets_row_factory():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        conn = get_connection(db_path)
        try:
            assert conn.row_factory is sqlite3.Row
        finally:
            conn.close()


def test_get_connection_enables_foreign_keys():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        conn = get_connection(db_path)
        try:
            result = conn.execute("PRAGMA foreign_keys").fetchone()
            assert result[0] == 1
        finally:
            conn.close()


def test_default_prefs_threshold_consistency():
    """DEFAULT_PREFS thresholds must match the module-level constants."""
    assert DEFAULT_PREFS["cold_threshold"] == COLD_TEMP_THRESHOLD
    assert DEFAULT_PREFS["hot_threshold"] == HOT_TEMP_THRESHOLD
    assert DEFAULT_PREFS["warm_threshold"] == WARM_TEMP_THRESHOLD


def test_default_prefs_has_all_expected_keys():
    expected_keys = {
        "cold_threshold", "warn_in_allday", "warn_rain", "warn_wind",
        "warn_cold", "warn_snow", "warn_sunny", "warn_hot",
        "show_allday_events", "timed_events_enabled",
        "allday_rain", "allday_wind", "allday_cold", "allday_snow",
        "allday_sunny", "allday_hot",
        "warm_threshold", "hot_threshold", "temp_unit",
        "reminder_allday_hour", "reminder_evening_hour", "reminder_timed_minutes",
    }
    assert set(DEFAULT_PREFS.keys()) == expected_keys
