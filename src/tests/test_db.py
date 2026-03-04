import sqlite3
from datetime import datetime

import pytest

from src.services.forecast_store import ForecastStore
from src.web.db import (
    check_password,
    create_feed_token,
    create_feedback_table,
    create_user,
    set_user_location,
    create_user_preferences_table,
    get_feed_token_by_user,
    get_rows_by_token,
    get_user_by_email,
    get_user_locations,
)


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    ForecastStore(db_path=path)
    create_user_preferences_table(path)
    create_feedback_table(path)
    return path


# --- User functions ---

def test_create_user_and_get_by_email(db_path):
    create_user(db_path, "alice@example.com", "password123456")
    user = get_user_by_email(db_path, "alice@example.com")
    assert user is not None
    assert user["email"] == "alice@example.com"
    assert user["is_active"] == 1


def test_create_user_duplicate_email_raises(db_path):
    create_user(db_path, "dup@example.com", "password123456")
    with pytest.raises(sqlite3.IntegrityError):
        create_user(db_path, "dup@example.com", "differentpassword123")


def test_get_user_by_email_inactive_not_returned(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO users (email, password_hash, created_at, is_active) VALUES (?, ?, ?, ?)",
        ("inactive@example.com", "fakehash", datetime.now().isoformat(), 0),
    )
    conn.commit()
    conn.close()
    assert get_user_by_email(db_path, "inactive@example.com") is None


def test_check_password_correct(db_path):
    create_user(db_path, "pw@example.com", "correctpassword123")
    user = get_user_by_email(db_path, "pw@example.com")
    assert check_password("correctpassword123", user["password_hash"])


def test_check_password_wrong(db_path):
    create_user(db_path, "pw2@example.com", "correctpassword123")
    user = get_user_by_email(db_path, "pw2@example.com")
    assert not check_password("wrongpassword123", user["password_hash"])


# --- Location functions ---

def test_create_and_get_user_locations(db_path):
    user_id = create_user(db_path, "loc@example.com", "password123456")
    set_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
    locations = get_user_locations(db_path, user_id)
    assert len(locations) == 1
    assert locations[0]["location"] == "Munich, Germany"
    assert locations[0]["lat"] == pytest.approx(48.137)
    assert locations[0]["lon"] == pytest.approx(11.576)
    assert locations[0]["timezone"] == "Europe/Berlin"


# --- Feed token functions ---

def test_create_feed_token_returns_string(db_path):
    user_id = create_user(db_path, "token@example.com", "password123456")
    token = create_feed_token(db_path, user_id)
    assert isinstance(token, str)
    assert len(token) > 0


def test_get_feed_token_by_user(db_path):
    user_id = create_user(db_path, "feedtoken@example.com", "password123456")
    token = create_feed_token(db_path, user_id)
    assert get_feed_token_by_user(db_path, user_id) == token


def test_get_rows_by_token(db_path):
    user_id = create_user(db_path, "rows@example.com", "password123456")
    set_user_location(db_path, user_id, "Berlin, Germany", 52.520, 13.405, "Europe/Berlin")
    token = create_feed_token(db_path, user_id)
    rows = get_rows_by_token(db_path, token)
    assert len(rows) == 1
    assert rows[0]["email"] == "rows@example.com"
    assert rows[0]["location"] == "Berlin, Germany"
