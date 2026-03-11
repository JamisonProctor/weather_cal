import os
import sqlite3

import pytest

from src.services.forecast_store import ForecastStore
from src.utils.location_management import get_locations, load_locations_from_db


def _insert_user(db_path, email, is_active=1):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO users (email, password_hash, created_at, is_active) VALUES (?, ?, ?, ?)",
        (email, "fakehash", "2026-01-01T00:00:00", is_active),
    )
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return user_id


def _insert_location(db_path, user_id, location, lat, lon, tz):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO user_locations (user_id, location, lat, lon, timezone, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, location, lat, lon, tz, "2026-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()


def test_load_locations_from_db_returns_active_locations(db_path):
    uid = _insert_user(db_path, "a@example.com")
    _insert_location(db_path, uid, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
    locs = load_locations_from_db(db_path)
    assert len(locs) == 1
    assert locs[0]["location"] == "Munich, Germany"
    assert locs[0]["lat"] == pytest.approx(48.137)
    assert locs[0]["timezone"] == "Europe/Berlin"


def test_load_locations_from_db_excludes_inactive_users(db_path):
    uid = _insert_user(db_path, "gone@example.com", is_active=0)
    _insert_location(db_path, uid, "Berlin, Germany", 52.52, 13.405, "Europe/Berlin")
    locs = load_locations_from_db(db_path)
    assert locs == []


def test_load_locations_from_db_bad_path_returns_empty(tmp_path):
    bad_path = str(tmp_path / "nonexistent" / "missing.db")
    locs = load_locations_from_db(bad_path)
    assert locs == []


def test_get_locations_falls_back_to_default_location(monkeypatch, tmp_path):
    bad_path = str(tmp_path / "empty.db")
    ForecastStore(db_path=bad_path)  # creates schema but no users
    monkeypatch.setenv("DB_PATH", bad_path)
    monkeypatch.setenv("DEFAULT_LOCATION", "Fallback City")
    locs = get_locations()
    assert len(locs) == 1
    assert locs[0]["location"] == "Fallback City"


def test_get_locations_raises_when_no_locations(monkeypatch, tmp_path):
    bad_path = str(tmp_path / "empty2.db")
    ForecastStore(db_path=bad_path)
    monkeypatch.setenv("DB_PATH", bad_path)
    monkeypatch.delenv("DEFAULT_LOCATION", raising=False)
    with pytest.raises(EnvironmentError, match="No locations available"):
        get_locations()
