import sqlite3
from datetime import datetime, timedelta

import pytest

from src.services.forecast_store import ForecastStore
from src.web.db import (
    _detect_calendar_app,
    check_password,
    create_feed_token,
    create_feedback_table,
    create_user,
    set_user_location,
    create_user_preferences_table,
    get_admin_stats,
    get_feed_token_by_user,
    get_rows_by_token,
    get_user_by_email,
    get_user_locations,
    get_user_preferences,
    increment_settings_clicks,
    update_feed_poll,
    upsert_user_preferences,
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


# --- Preferences ---

def test_upsert_preferences_with_temp_unit(db_path):
    user_id = create_user(db_path, "prefs_unit@example.com", "password123456")
    upsert_user_preferences(
        db_path, user_id,
        cold_threshold=3.0, warn_in_allday=1, warn_rain=1, warn_wind=1,
        warn_cold=1, warn_snow=1, warn_sunny=0, temp_unit="F",
    )
    prefs = get_user_preferences(db_path, user_id)
    assert prefs["temp_unit"] == "F"


# --- Analytics functions ---

def test_update_feed_poll_increments_count(db_path):
    user_id = create_user(db_path, "poll@example.com", "password123456")
    token = create_feed_token(db_path, user_id)
    update_feed_poll(db_path, token, "TestAgent/1.0")
    update_feed_poll(db_path, token, "TestAgent/1.0")
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT poll_count, last_user_agent FROM feed_tokens WHERE token = ?", (token,)).fetchone()
    conn.close()
    assert row[0] == 2
    assert row[1] == "TestAgent/1.0"


def test_update_feed_poll_unknown_token_is_noop(db_path):
    # Should not raise even for an invalid token
    update_feed_poll(db_path, "nonexistent-token", "agent")


def test_increment_settings_clicks(db_path):
    user_id = create_user(db_path, "clicks@example.com", "password123456")
    create_feed_token(db_path, user_id)
    increment_settings_clicks(db_path, user_id)
    increment_settings_clicks(db_path, user_id)
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT settings_clicks FROM feed_tokens WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    assert row[0] == 2


def test_get_admin_stats_empty_db(db_path):
    stats = get_admin_stats(db_path)
    assert stats["total_users"] == 0
    assert stats["unique_locations"] == 0
    assert stats["changed_prefs_count"] == 0
    assert stats["total_polls"] == 0
    assert stats["avg_polls_per_day"] == 0.0
    assert stats["total_settings_clicks"] == 0
    assert stats["users"] == []


def test_get_admin_stats_with_user(db_path):
    user_id = create_user(db_path, "admin_stat@example.com", "password123456")
    set_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
    token = create_feed_token(db_path, user_id)
    update_feed_poll(db_path, token, "CFNetwork/1.0 Darwin")
    stats = get_admin_stats(db_path)
    assert stats["total_users"] == 1
    assert stats["unique_locations"] == 1
    assert stats["total_polls"] == 1
    assert len(stats["users"]) == 1
    u = stats["users"][0]
    assert u["email"] == "admin_stat@example.com"
    assert u["location"] == "Munich, Germany"
    assert u["poll_count"] == 1
    assert u["calendar_app"] == "Apple Calendar"
    assert u["changed_prefs"] is False
    # Same-day signup: polls_per_day = 1/1 = 1.0, not flagged
    assert u["polls_per_day"] == 1.0
    assert u["low_polls"] is False


def _backdate_token(db_path, token, days_ago):
    """Set a feed token's created_at to N days ago."""
    old_date = (datetime.now() - timedelta(days=days_ago)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE feed_tokens SET created_at = ? WHERE token = ?", (old_date, token))
    conn.commit()
    conn.close()


def test_admin_stats_polls_per_day_old_account(db_path):
    """Account 10 days old with 20 polls → 2.0 polls/day, not flagged."""
    user_id = create_user(db_path, "old@example.com", "password123456")
    set_user_location(db_path, user_id, "Berlin, Germany", 52.52, 13.405, "Europe/Berlin")
    token = create_feed_token(db_path, user_id)
    _backdate_token(db_path, token, 10)
    for _ in range(20):
        update_feed_poll(db_path, token, "CFNetwork/1.0")
    stats = get_admin_stats(db_path)
    u = stats["users"][0]
    assert u["polls_per_day"] == 2.0
    assert u["low_polls"] is False


def test_admin_stats_low_polls_flag(db_path):
    """Account 5 days old with 2 polls → 0.4 polls/day, flagged."""
    user_id = create_user(db_path, "low@example.com", "password123456")
    set_user_location(db_path, user_id, "Berlin, Germany", 52.52, 13.405, "Europe/Berlin")
    token = create_feed_token(db_path, user_id)
    _backdate_token(db_path, token, 5)
    for _ in range(2):
        update_feed_poll(db_path, token, "CFNetwork/1.0")
    stats = get_admin_stats(db_path)
    u = stats["users"][0]
    assert u["polls_per_day"] == 0.4
    assert u["low_polls"] is True


def test_admin_stats_new_account_not_flagged(db_path):
    """Account < 1 day old with 0 polls should NOT be flagged."""
    user_id = create_user(db_path, "new@example.com", "password123456")
    set_user_location(db_path, user_id, "Berlin, Germany", 52.52, 13.405, "Europe/Berlin")
    create_feed_token(db_path, user_id)
    stats = get_admin_stats(db_path)
    u = stats["users"][0]
    assert u["polls_per_day"] == 0.0
    assert u["low_polls"] is False


def test_admin_stats_avg_polls_per_day(db_path):
    """Avg polls/day across two users with different rates."""
    uid1 = create_user(db_path, "u1@example.com", "password123456")
    set_user_location(db_path, uid1, "Berlin, Germany", 52.52, 13.405, "Europe/Berlin")
    t1 = create_feed_token(db_path, uid1)
    _backdate_token(db_path, t1, 10)
    for _ in range(20):
        update_feed_poll(db_path, t1, "CFNetwork/1.0")

    uid2 = create_user(db_path, "u2@example.com", "password123456")
    set_user_location(db_path, uid2, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
    t2 = create_feed_token(db_path, uid2)
    _backdate_token(db_path, t2, 10)
    for _ in range(10):
        update_feed_poll(db_path, t2, "CFNetwork/1.0")

    stats = get_admin_stats(db_path)
    # User1: 20/10=2.0, User2: 10/10=1.0, avg = (2.0+1.0)/2 = 1.5
    assert stats["avg_polls_per_day"] == 1.5


# --- Calendar app detection ---

def test_detect_calendar_app_apple():
    assert _detect_calendar_app("CFNetwork/1.0 Darwin/21.0") == "Apple Calendar"
    assert _detect_calendar_app("CalendarStore") == "Apple Calendar"


def test_detect_calendar_app_google():
    assert _detect_calendar_app("Google-Calendar-Importer") == "Google Calendar"


def test_detect_calendar_app_fantastical():
    assert _detect_calendar_app("Fantastical/3.0") == "Fantastical"


def test_detect_calendar_app_empty():
    assert _detect_calendar_app("") == "Unknown"
    assert _detect_calendar_app("   ") == "Unknown"


def test_detect_calendar_app_unknown():
    assert _detect_calendar_app("SomeOtherApp/2.0") == "Other"


# --- Account management ---

def test_update_user_email_success(db_path):
    from src.web.db import update_user_email
    user_id = create_user(db_path, "old@example.com", "password123456")
    update_user_email(db_path, user_id, "new@example.com")
    assert get_user_by_email(db_path, "old@example.com") is None
    assert get_user_by_email(db_path, "new@example.com") is not None


def test_update_user_email_duplicate_raises(db_path):
    from src.web.db import update_user_email
    create_user(db_path, "taken@example.com", "password123456")
    user_id = create_user(db_path, "other@example.com", "password123456")
    with pytest.raises(sqlite3.IntegrityError):
        update_user_email(db_path, user_id, "taken@example.com")


def test_update_user_password_success(db_path):
    from src.web.db import update_user_password
    user_id = create_user(db_path, "pwchange@example.com", "oldpassword12345")
    update_user_password(db_path, user_id, "newpassword12345")
    user = get_user_by_email(db_path, "pwchange@example.com")
    assert check_password("newpassword12345", user["password_hash"])
    assert not check_password("oldpassword12345", user["password_hash"])


def test_delete_user_account_soft_deletes(db_path):
    from src.web.db import delete_user_account
    user_id = create_user(db_path, "del@example.com", "password123456")
    delete_user_account(db_path, user_id)
    assert get_user_by_email(db_path, "del@example.com") is None
    # Verify is_active = 0 (not actually deleted)
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT is_active FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    assert row[0] == 0


def test_delete_user_account_removes_feed_token(db_path):
    from src.web.db import delete_user_account
    user_id = create_user(db_path, "deltok@example.com", "password123456")
    create_feed_token(db_path, user_id)
    assert get_feed_token_by_user(db_path, user_id) is not None
    delete_user_account(db_path, user_id)
    assert get_feed_token_by_user(db_path, user_id) is None


def test_get_user_by_id_active(db_path):
    from src.web.db import get_user_by_id
    user_id = create_user(db_path, "byid@example.com", "password123456")
    user = get_user_by_id(db_path, user_id)
    assert user is not None
    assert user["email"] == "byid@example.com"


def test_get_user_by_id_inactive_returns_none(db_path):
    from src.web.db import get_user_by_id, delete_user_account
    user_id = create_user(db_path, "inactive_id@example.com", "password123456")
    delete_user_account(db_path, user_id)
    assert get_user_by_id(db_path, user_id) is None


def test_save_feedback_inserts_row(db_path):
    from src.web.db import save_feedback
    user_id = create_user(db_path, "fb@example.com", "password123456")
    save_feedback(
        db_path, user_id, "fb@example.com",
        feed_url="webcal://example.com/feed/abc/weather.ics",
        locations="Munich, Germany",
        calendar_app="Apple Calendar",
        description="Love it!",
        user_agent="TestAgent/1.0",
        platform="macOS",
        screen_width="1920",
        screen_height="1080",
        timezone="Europe/Berlin",
    )
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT description FROM feedback WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    assert row[0] == "Love it!"


def test_get_last_forecast_update_empty_locations(db_path):
    from src.web.db import get_last_forecast_update
    assert get_last_forecast_update(db_path, []) is None


def test_get_last_forecast_update_with_data(db_path):
    from src.web.db import get_last_forecast_update
    from src.models.forecast import Forecast
    store = ForecastStore(db_path=db_path)
    store.upsert_forecast(Forecast(
        date="2099-01-01", location="Munich, Germany",
        high=10, low=2, summary="Test", description="Test",
        fetch_time="2099-01-01T12:00:00",
    ))
    store.upsert_forecast(Forecast(
        date="2099-01-02", location="Munich, Germany",
        high=12, low=3, summary="Test2", description="Test2",
        fetch_time="2099-01-02T08:00:00",
    ))
    result = get_last_forecast_update(db_path, ["Munich, Germany"])
    assert result == "2099-01-02T08:00:00"
