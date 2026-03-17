import sqlite3
from datetime import datetime, timedelta

import pytest

from src.services.forecast_store import ForecastStore
from src.web.db import (
    _detect_calendar_app,
    check_password,
    create_feed_token,
    create_user,
    set_user_location,
    get_admin_stats,
    get_admin_users_for_export,
    get_feed_token_by_user,
    get_funnel_by_source,
    get_funnel_stats,
    get_funnel_timeseries,
    get_page_view_stats,
    get_rows_by_token,
    get_user_by_email,
    get_user_locations,
    get_user_preferences,
    increment_page_view,
    increment_settings_clicks,
    log_feed_poll,
    log_funnel_event,
    update_feed_poll,
    upsert_user_preferences,
)


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
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    locations = get_user_locations(db_path, user_id)
    assert len(locations) == 1
    assert locations[0]["location"] == "Munich"
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
    set_user_location(db_path, user_id, "Berlin", 52.520, 13.405, "Europe/Berlin")
    token = create_feed_token(db_path, user_id)
    rows = get_rows_by_token(db_path, token)
    assert len(rows) == 1
    assert rows[0]["email"] == "rows@example.com"
    assert rows[0]["location"] == "Berlin"


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


def test_log_feed_poll_inserts_rows(db_path):
    user_id = create_user(db_path, "logpoll@example.com", "password123456")
    token = create_feed_token(db_path, user_id)
    log_feed_poll(db_path, token, "TestAgent/1.0")
    log_feed_poll(db_path, token, "TestAgent/1.0")
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT * FROM poll_log WHERE token = ?", (token,)).fetchall()
    conn.close()
    assert len(rows) == 2


def test_admin_stats_include_poll_log_fields(db_path):
    user_id = create_user(db_path, "logstats@example.com", "password123456")
    set_user_location(db_path, user_id, "Berlin", 52.52, 13.405, "Europe/Berlin")
    token = create_feed_token(db_path, user_id)
    log_feed_poll(db_path, token, "Agent")
    log_feed_poll(db_path, token, "Agent")
    stats = get_admin_stats(db_path)
    u = stats["users"][0]
    assert u["polls_last_24h"] == 2


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
    assert stats["total_settings_clicks"] == 0
    assert stats["users"] == []


def test_get_admin_stats_with_user(db_path):
    user_id = create_user(db_path, "admin_stat@example.com", "password123456")
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    token = create_feed_token(db_path, user_id)
    update_feed_poll(db_path, token, "CFNetwork/1.0 Darwin")
    stats = get_admin_stats(db_path)
    assert stats["total_users"] == 1
    assert stats["unique_locations"] == 1
    assert stats["total_polls"] == 1
    assert len(stats["users"]) == 1
    u = stats["users"][0]
    assert u["email"] == "admin_stat@example.com"
    assert u["location"] == "Munich"
    assert u["poll_count"] == 1
    assert u["calendar_app"] == "Apple Calendar"
    assert u["changed_prefs"] is False
    assert u["low_polls"] is False


def _backdate_token(db_path, token, days_ago):
    """Set a feed token's created_at to N days ago."""
    old_date = (datetime.now() - timedelta(days=days_ago)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE feed_tokens SET created_at = ? WHERE token = ?", (old_date, token))
    conn.commit()
    conn.close()


def test_admin_stats_polls_last_24h_with_recent_polls(db_path):
    """Recent poll_log entries show up in polls_last_24h, not flagged."""
    user_id = create_user(db_path, "recent@example.com", "password123456")
    set_user_location(db_path, user_id, "Berlin", 52.52, 13.405, "Europe/Berlin")
    token = create_feed_token(db_path, user_id)
    _backdate_token(db_path, token, 10)
    log_feed_poll(db_path, token, "CFNetwork/1.0")
    log_feed_poll(db_path, token, "CFNetwork/1.0")
    stats = get_admin_stats(db_path)
    u = stats["users"][0]
    assert u["polls_last_24h"] == 2
    assert u["low_polls"] is False


def test_admin_stats_low_polls_flag(db_path):
    """Account > 1 day old with 0 polls in last 24h → flagged."""
    user_id = create_user(db_path, "low@example.com", "password123456")
    set_user_location(db_path, user_id, "Berlin", 52.52, 13.405, "Europe/Berlin")
    token = create_feed_token(db_path, user_id)
    _backdate_token(db_path, token, 5)
    # No poll_log entries in last 24h
    stats = get_admin_stats(db_path)
    u = stats["users"][0]
    assert u["polls_last_24h"] == 0
    assert u["low_polls"] is True


def test_admin_stats_new_account_not_flagged(db_path):
    """Account < 1 day old with 0 polls should NOT be flagged."""
    user_id = create_user(db_path, "new@example.com", "password123456")
    set_user_location(db_path, user_id, "Berlin", 52.52, 13.405, "Europe/Berlin")
    create_feed_token(db_path, user_id)
    stats = get_admin_stats(db_path)
    u = stats["users"][0]
    assert u["polls_last_24h"] == 0
    assert u["low_polls"] is False


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
        locations="Munich",
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
        date="2099-01-01", location="Munich",
        high=10, low=2, summary="Test", description="Test",
        fetch_time="2099-01-01T12:00:00",
    ))
    store.upsert_forecast(Forecast(
        date="2099-01-02", location="Munich",
        high=12, low=3, summary="Test2", description="Test2",
        fetch_time="2099-01-02T08:00:00",
    ))
    result = get_last_forecast_update(db_path, ["Munich"])
    assert result == "2099-01-02T08:00:00"


# --- Admin Google status tests ---


def test_admin_stats_includes_google_status_active(db_path):
    user_id = create_user(db_path, "gactive@example.com", "password123456")
    set_user_location(db_path, user_id, "Berlin", 52.52, 13.405, "Europe/Berlin")
    create_feed_token(db_path, user_id)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO google_tokens (user_id, access_token, refresh_token, status, connected_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, "tok", "ref", "active", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()
    stats = get_admin_stats(db_path)
    user = next(u for u in stats["users"] if u["email"] == "gactive@example.com")
    assert user["google_status"] == "active"


def test_admin_stats_includes_google_status_revoked(db_path):
    user_id = create_user(db_path, "grevoked@example.com", "password123456")
    set_user_location(db_path, user_id, "Berlin", 52.52, 13.405, "Europe/Berlin")
    create_feed_token(db_path, user_id)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO google_tokens (user_id, access_token, refresh_token, status, connected_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, "tok", "ref", "revoked", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()
    stats = get_admin_stats(db_path)
    user = next(u for u in stats["users"] if u["email"] == "grevoked@example.com")
    assert user["google_status"] == "revoked"


def test_admin_stats_includes_google_status_none(db_path):
    user_id = create_user(db_path, "gnone@example.com", "password123456")
    set_user_location(db_path, user_id, "Berlin", 52.52, 13.405, "Europe/Berlin")
    create_feed_token(db_path, user_id)
    stats = get_admin_stats(db_path)
    user = next(u for u in stats["users"] if u["email"] == "gnone@example.com")
    assert user["google_status"] is None


def test_admin_stats_google_connected_count(db_path):
    # User 1: active
    uid1 = create_user(db_path, "gc1@example.com", "password123456")
    set_user_location(db_path, uid1, "Berlin", 52.52, 13.405, "Europe/Berlin")
    create_feed_token(db_path, uid1)
    # User 2: revoked
    uid2 = create_user(db_path, "gc2@example.com", "password123456")
    set_user_location(db_path, uid2, "Berlin", 52.52, 13.405, "Europe/Berlin")
    create_feed_token(db_path, uid2)
    # User 3: no google token
    uid3 = create_user(db_path, "gc3@example.com", "password123456")
    set_user_location(db_path, uid3, "Berlin", 52.52, 13.405, "Europe/Berlin")
    create_feed_token(db_path, uid3)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO google_tokens (user_id, access_token, refresh_token, status, connected_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (uid1, "tok", "ref", "active", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
    )
    conn.execute(
        "INSERT INTO google_tokens (user_id, access_token, refresh_token, status, connected_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (uid2, "tok", "ref", "revoked", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()
    stats = get_admin_stats(db_path)
    assert stats["google_connected_count"] == 1


# --- UTM tracking ---


def test_create_user_stores_utm_params(db_path):
    user_id = create_user(
        db_path, "utm@example.com", "password123456",
        utm_source="twitter", utm_medium="social", utm_campaign="launch",
        referrer="https://twitter.com/someone",
    )
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT utm_source, utm_medium, utm_campaign, referrer FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    assert row[0] == "twitter"
    assert row[1] == "social"
    assert row[2] == "launch"
    assert row[3] == "https://twitter.com/someone"


def test_create_user_without_utm_params(db_path):
    user_id = create_user(db_path, "noutm@example.com", "password123456")
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT utm_source, utm_medium, utm_campaign, referrer FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    assert row[0] is None
    assert row[1] is None
    assert row[2] is None
    assert row[3] is None


def test_admin_stats_includes_utm_source(db_path):
    user_id = create_user(db_path, "utmadmin@example.com", "password123456", utm_source="reddit")
    set_user_location(db_path, user_id, "Berlin", 52.52, 13.405, "Europe/Berlin")
    create_feed_token(db_path, user_id)
    stats = get_admin_stats(db_path)
    user = next(u for u in stats["users"] if u["email"] == "utmadmin@example.com")
    assert user["utm_source"] == "reddit"


# --- Funnel events ---


def test_log_funnel_event_and_get_stats(db_path):
    uid1 = create_user(db_path, "funnel1@example.com", "password123456")
    uid2 = create_user(db_path, "funnel2@example.com", "password123456")
    log_funnel_event(db_path, uid1, "signup_completed")
    log_funnel_event(db_path, uid2, "signup_completed")
    log_funnel_event(db_path, uid1, "location_set")
    log_funnel_event(db_path, uid1, "feed_subscribed")
    stats = get_funnel_stats(db_path)
    assert stats["signup_completed"] == 2
    assert stats["location_set"] == 1
    assert stats["feed_subscribed"] == 1
    assert stats["google_connected"] == 0
    assert stats["pct_location"] == 50
    assert stats["pct_feed"] == 50
    assert stats["pct_google"] == 0


def test_get_funnel_stats_empty(db_path):
    stats = get_funnel_stats(db_path)
    assert stats["signup_completed"] == 0
    assert stats["pct_location"] == 0


# --- Funnel timeseries ---


def test_get_funnel_timeseries_empty_db(db_path):
    rows = get_funnel_timeseries(db_path, days=7)
    assert len(rows) == 7
    assert all(r["signups"] == 0 for r in rows)
    assert all(r["location_set"] == 0 for r in rows)


def test_get_funnel_timeseries_events_land_on_correct_day(db_path):
    uid = create_user(db_path, "ts@example.com", "password123456")
    log_funnel_event(db_path, uid, "signup_completed")
    rows = get_funnel_timeseries(db_path, days=7)
    today = datetime.now().date().isoformat()
    today_row = next(r for r in rows if r["date"] == today)
    assert today_row["signups"] == 1


def test_get_funnel_timeseries_days_param_limits_range(db_path):
    rows_7 = get_funnel_timeseries(db_path, days=7)
    rows_30 = get_funnel_timeseries(db_path, days=30)
    assert len(rows_7) == 7
    assert len(rows_30) == 30


# --- Funnel by source ---


def test_get_funnel_by_source_empty(db_path):
    result = get_funnel_by_source(db_path)
    assert result == []


def test_get_funnel_by_source_groups_by_utm_source(db_path):
    uid1 = create_user(db_path, "src1@example.com", "password123456", utm_source="twitter")
    uid2 = create_user(db_path, "src2@example.com", "password123456")
    log_funnel_event(db_path, uid1, "signup_completed")
    log_funnel_event(db_path, uid2, "signup_completed")
    log_funnel_event(db_path, uid1, "location_set")
    result = get_funnel_by_source(db_path)
    sources = {r["source"]: r for r in result}
    assert "twitter" in sources
    assert "direct" in sources
    assert sources["twitter"]["signups"] == 1
    assert sources["twitter"]["location_set"] == 1
    assert sources["direct"]["signups"] == 1


# --- Page views ---


def test_increment_page_view_creates_row(db_path):
    increment_page_view(db_path, "/")
    stats = get_page_view_stats(db_path)
    assert stats["today"].get("/") == 1
    assert stats["total"].get("/") == 1


def test_increment_page_view_increments_existing(db_path):
    increment_page_view(db_path, "/")
    increment_page_view(db_path, "/")
    increment_page_view(db_path, "/signup")
    stats = get_page_view_stats(db_path)
    assert stats["today"]["/"] == 2
    assert stats["today"]["/signup"] == 1
    assert stats["total"]["/"] == 2


def test_get_page_view_stats_empty(db_path):
    stats = get_page_view_stats(db_path)
    assert stats["total"] == {}
    assert stats["today"] == {}


# --- Admin users export ---


def test_get_admin_users_for_export_returns_expected_keys(db_path):
    uid = create_user(db_path, "exp@example.com", "password123456")
    set_user_location(db_path, uid, "Berlin", 52.52, 13.405, "Europe/Berlin")
    create_feed_token(db_path, uid)
    users = get_admin_users_for_export(db_path)
    assert len(users) == 1
    u = users[0]
    assert "email" in u
    assert "location" in u
    assert "utm_source" in u
    assert "calendar_app" in u
    assert "settings_clicks" in u
    assert u["email"] == "exp@example.com"
