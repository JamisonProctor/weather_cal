import sqlite3

import pytest

import src.web.app as web_app
from src.constants import DEFAULT_PREFS
from src.models.forecast import Forecast
from src.services.forecast_store import ForecastStore
from src.integrations.google_push import store_google_tokens
from src.web.db import (
    check_password,
    create_feed_token,
    create_user,
    delete_user_account,
    export_user_data,
    set_user_location,
    get_feed_token_by_user,
    get_user_by_email,
    get_user_by_id,
    get_user_preferences,
    log_feed_poll,
    save_feedback,
    upsert_user_preferences,
)


# --- Signup ---

def test_signup_redirects_to_setup(client):
    resp = client.post("/signup", data={"email": "new@example.com", "password": "supersecretpass1"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/setup"


def test_signup_short_password_returns_422(client):
    resp = client.post("/signup", data={"email": "short@example.com", "password": "tooshort"})
    assert resp.status_code == 422


def test_signup_duplicate_email_returns_422(client):
    client.post("/signup", data={"email": "dup@example.com", "password": "supersecretpass1"})
    resp = client.post("/signup", data={"email": "dup@example.com", "password": "supersecretpass1"})
    assert resp.status_code == 422


# --- Login ---

def test_login_valid_credentials_redirect(client, db_path):
    create_user(db_path, "login@example.com", "supersecretpass1")
    resp = client.post("/login", data={"email": "login@example.com", "password": "supersecretpass1"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings"


def test_login_invalid_credentials_returns_401(client, db_path):
    create_user(db_path, "badlogin@example.com", "supersecretpass1")
    resp = client.post("/login", data={"email": "badlogin@example.com", "password": "wrongpassword123"})
    assert resp.status_code == 401


def test_logout_redirects_to_landing(client, auth_cookies):
    _, cookies = auth_cookies(email="logout@example.com")
    resp = client.post("/logout", cookies=cookies)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_logout_clears_session_cookie(client, auth_cookies):
    _, cookies = auth_cookies(email="logout2@example.com")
    resp = client.post("/logout", cookies=cookies)
    assert resp.status_code == 303
    # Response should include a Set-Cookie header that expires the session cookie
    set_cookie = resp.headers.get("set-cookie", "")
    assert "session=" in set_cookie
    assert ('max-age=0' in set_cookie.lower() or 'expires=' in set_cookie.lower())


# --- Settings ---

def test_settings_get_requires_auth(client):
    resp = client.get("/settings")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_settings_post_saves_preferences(client, db_path, auth_cookies):
    user_id, cookies = auth_cookies()
    resp = client.post(
        "/settings",
        data={
            "cold_threshold": "5.0",
            "warn_in_allday": "on",
            "warn_rain": "on",
            "warn_wind": "",
            "warn_cold": "on",
            "warn_snow": "",
            "warn_sunny": "on",
            "show_allday_events": "on",
            "timed_events_enabled": "on",
            "allday_rain": "on",
            "allday_wind": "",
            "allday_cold": "on",
            "allday_snow": "on",
            "allday_sunny": "",
        },
        cookies=cookies,
    )
    assert resp.status_code == 303
    prefs = get_user_preferences(db_path, user_id)
    assert prefs is not None
    assert prefs["cold_threshold"] == 5.0
    assert prefs["warn_rain"] == 1
    assert prefs["warn_wind"] == 0
    assert prefs["warn_sunny"] == 1
    assert prefs["show_allday_events"] == 1
    assert prefs["timed_events_enabled"] == 1
    assert prefs["allday_rain"] == 1
    assert prefs["allday_wind"] == 0
    assert prefs["allday_cold"] == 1


def test_settings_post_saves_reminder_preferences(client, db_path, auth_cookies):
    user_id, cookies = auth_cookies()
    resp = client.post(
        "/settings",
        data={
            "cold_threshold": "3.0",
            "reminder_allday_hour": "7",
            "reminder_timed_minutes": "15",
        },
        cookies=cookies,
    )
    assert resp.status_code == 303
    prefs = get_user_preferences(db_path, user_id)
    assert prefs["reminder_allday_hour"] == 7
    assert prefs["reminder_timed_minutes"] == 15


def test_settings_post_saves_evening_reminder(client, db_path, auth_cookies):
    user_id, cookies = auth_cookies()
    resp = client.post(
        "/settings",
        data={
            "cold_threshold": "3.0",
            "reminder_evening_hour": "20",
        },
        cookies=cookies,
    )
    assert resp.status_code == 303
    prefs = get_user_preferences(db_path, user_id)
    assert prefs["reminder_evening_hour"] == 20


def test_settings_post_midnight_checkbox_sets_allday_hour_zero(client, db_path, auth_cookies):
    user_id, cookies = auth_cookies()
    resp = client.post(
        "/settings",
        data={
            "cold_threshold": "3.0",
            "reminder_allday_hour": "-1",
            "reminder_allday_midnight": "on",
        },
        cookies=cookies,
    )
    assert resp.status_code == 303
    prefs = get_user_preferences(db_path, user_id)
    assert prefs["reminder_allday_hour"] == 0


def test_settings_post_reminder_defaults_to_minus_one(client, db_path, auth_cookies):
    user_id, cookies = auth_cookies()
    resp = client.post(
        "/settings",
        data={"cold_threshold": "3.0"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    prefs = get_user_preferences(db_path, user_id)
    assert prefs["reminder_allday_hour"] == -1
    assert prefs["reminder_evening_hour"] == -1
    assert prefs["reminder_timed_minutes"] == -1


# --- Setup ---

def test_setup_post_first_time_redirects_to_connect(client, db_path, auth_cookies):
    _, cookies = auth_cookies()
    resp = client.post(
        "/setup",
        data={
            "location": "Munich",
            "lat": "48.137",
            "lon": "11.576",
            "timezone": "Europe/Berlin",
        },
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/connect?from=setup"


def test_setup_post_location_change_redirects_to_settings(client, db_path, auth_cookies):
    user_id, cookies = auth_cookies()
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    resp = client.post(
        "/setup",
        data={
            "location": "Berlin",
            "lat": "52.520",
            "lon": "13.405",
            "timezone": "Europe/Berlin",
        },
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings"


# --- Feed ---

def test_feed_invalid_token_returns_404(client):
    resp = client.get("/feed/invalid-token-abc/weather.ics")
    assert resp.status_code == 404


def test_feed_valid_token_returns_ics(client, db_path, auth_cookies):
    user_id, _ = auth_cookies()
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    token = create_feed_token(db_path, user_id)

    store = ForecastStore(db_path=db_path)
    store.upsert_forecast(Forecast(
        date="2099-01-01",
        location="Munich",
        high=10,
        low=2,
        summary="Test",
        description="Test forecast",
        times=["2099-01-01T12:00"],
        temps=[10],
        codes=[1],
        rain=[0],
        winds=[5],
        timezone="Europe/Berlin",
    ))

    resp = client.get(f"/feed/{token}/weather.ics")
    assert resp.status_code == 200
    assert "text/calendar" in resp.headers["content-type"]


def test_feed_records_poll(client, db_path, auth_cookies):
    user_id, _ = auth_cookies()
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    token = create_feed_token(db_path, user_id)

    store = ForecastStore(db_path=db_path)
    store.upsert_forecast(Forecast(
        date="2099-01-01",
        location="Munich",
        high=10, low=2,
        summary="Test", description="Test",
        times=["2099-01-01T12:00"], temps=[10], codes=[1], rain=[0], winds=[5],
        timezone="Europe/Berlin",
    ))

    client.get(f"/feed/{token}/weather.ics", headers={"user-agent": "TestAgent/1.0"})
    client.get(f"/feed/{token}/weather.ics", headers={"user-agent": "TestAgent/1.0"})

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT poll_count FROM feed_tokens WHERE token = ?", (token,)).fetchone()
    assert row[0] == 2
    poll_log_rows = conn.execute("SELECT * FROM poll_log WHERE token = ?", (token,)).fetchall()
    conn.close()
    assert len(poll_log_rows) == 2


def test_settings_ref_cal_increments_clicks(client, db_path, auth_cookies):
    user_id, cookies = auth_cookies()
    token = create_feed_token(db_path, user_id)
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")

    client.get("/settings?ref=cal", cookies=cookies)
    client.get("/settings?ref=cal", cookies=cookies)

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT settings_clicks FROM feed_tokens WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    assert row[0] == 2


def test_setup_us_location_sets_fahrenheit(client, db_path, auth_cookies):
    _, cookies = auth_cookies(email="us@example.com")
    client.post(
        "/setup",
        data={
            "location": "New York, New York, United States",
            "lat": "40.713",
            "lon": "-74.006",
            "timezone": "America/New_York",
            "country": "United States",
        },
        cookies=cookies,
    )
    user = get_user_by_email(db_path, "us@example.com")
    prefs = get_user_preferences(db_path, user["id"])
    assert prefs is not None
    assert prefs["temp_unit"] == "F"


def test_setup_non_us_location_does_not_set_fahrenheit(client, db_path, auth_cookies):
    _, cookies = auth_cookies(email="de@example.com")
    client.post(
        "/setup",
        data={
            "location": "Munich, Bavaria, Germany",
            "lat": "48.137",
            "lon": "11.576",
            "timezone": "Europe/Berlin",
            "country": "Germany",
        },
        cookies=cookies,
    )
    user = get_user_by_email(db_path, "de@example.com")
    prefs = get_user_preferences(db_path, user["id"])
    assert prefs is None  # no prefs auto-created for non-US


def test_settings_saves_temp_unit_fahrenheit(client, db_path, auth_cookies):
    user_id, cookies = auth_cookies()
    # 37.4°F = 3°C, 57.2°F = 14°C, 82.4°F = 28°C
    resp = client.post(
        "/settings",
        data={
            "cold_threshold": "37.4",
            "warm_threshold": "57.2",
            "hot_threshold": "82.4",
            "temp_unit": "F",
            "warn_in_allday": "on",
            "warn_rain": "on",
            "warn_wind": "on",
            "warn_cold": "on",
            "warn_snow": "on",
            "warn_sunny": "",
            "show_allday_events": "on",
            "timed_events_enabled": "on",
            "allday_rain": "on",
            "allday_wind": "on",
            "allday_cold": "on",
            "allday_snow": "on",
            "allday_sunny": "",
        },
        cookies=cookies,
    )
    assert resp.status_code == 303
    prefs = get_user_preferences(db_path, user_id)
    assert prefs["temp_unit"] == "F"
    assert abs(prefs["cold_threshold"] - 3.0) < 0.01
    assert abs(prefs["warm_threshold"] - 14.0) < 0.01
    assert abs(prefs["hot_threshold"] - 28.0) < 0.01


def test_admin_route_requires_auth(client):
    resp = client.get("/admin")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_admin_route_forbidden_for_non_admin(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    _, cookies = auth_cookies(email="user@example.com")
    resp = client.get("/admin", cookies=cookies)
    assert resp.status_code == 403


def test_admin_route_accessible_for_admin(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    _, cookies = auth_cookies(email="admin@example.com")
    resp = client.get("/admin", cookies=cookies)
    assert resp.status_code == 200
    assert b"Admin" in resp.content


def test_admin_shows_feedback(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    _, cookies = auth_cookies(email="admin@example.com")
    from src.web.db import save_feedback
    save_feedback(db_path, 1, "sender@example.com", "", "Berlin", "Apple Calendar", "Love this app!", "", "", "", "", "")
    resp = client.get("/admin", cookies=cookies)
    assert resp.status_code == 200
    assert b"sender@example.com" in resp.content
    assert b"Love this app!" in resp.content


def test_admin_shows_no_feedback_message(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    _, cookies = auth_cookies(email="admin@example.com")
    resp = client.get("/admin", cookies=cookies)
    assert resp.status_code == 200
    assert b"No feedback yet." in resp.content


# --- Welcome email ---

def test_setup_triggers_welcome_email_on_first_setup(client, db_path, monkeypatch, auth_cookies):
    """Welcome email is sent once on first location setup when ENABLE_WELCOME_EMAIL is set."""
    calls = []
    monkeypatch.setenv("ENABLE_WELCOME_EMAIL", "true")
    monkeypatch.setattr(web_app, "send_welcome_email", lambda *a, **kw: calls.append(a))

    user_id, cookies = auth_cookies(email="welcome@example.com")
    create_feed_token(db_path, user_id)
    client.post(
        "/setup",
        data={
            "location": "Munich",
            "lat": "48.137",
            "lon": "11.576",
            "timezone": "Europe/Berlin",
        },
        cookies=cookies,
    )
    assert len(calls) == 1
    assert calls[0][0] == "welcome@example.com"


# --- Account management routes ---

def test_settings_email_change_success(client, db_path, auth_cookies):
    user_id, cookies = auth_cookies(email="emailchange@example.com")
    resp = client.post(
        "/settings/email",
        data={"new_email": "changed@example.com", "current_password": "supersecretpass1"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert "success=email" in resp.headers["location"]
    assert get_user_by_email(db_path, "changed@example.com") is not None


def test_settings_email_change_wrong_password(client, db_path, auth_cookies):
    _, cookies = auth_cookies(email="emailwrong@example.com")
    resp = client.post(
        "/settings/email",
        data={"new_email": "new@example.com", "current_password": "wrongpassword123"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert "error=wrong_password" in resp.headers["location"]


def test_settings_email_change_duplicate_email(client, db_path, auth_cookies):
    create_user(db_path, "existing@example.com", "password123456")
    _, cookies = auth_cookies(email="emaildup@example.com")
    resp = client.post(
        "/settings/email",
        data={"new_email": "existing@example.com", "current_password": "supersecretpass1"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert "error=email_taken" in resp.headers["location"]


def test_settings_email_change_requires_auth(client):
    resp = client.post(
        "/settings/email",
        data={"new_email": "x@example.com", "current_password": "password123456"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_settings_password_change_success(client, db_path, auth_cookies):
    user_id, cookies = auth_cookies(email="pwchange@example.com")
    resp = client.post(
        "/settings/password",
        data={"current_password": "supersecretpass1", "new_password": "newlongpassword1"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert "success=password" in resp.headers["location"]
    user = get_user_by_email(db_path, "pwchange@example.com")
    assert check_password("newlongpassword1", user["password_hash"])


def test_settings_password_change_wrong_current(client, db_path, auth_cookies):
    _, cookies = auth_cookies(email="pwwrong@example.com")
    resp = client.post(
        "/settings/password",
        data={"current_password": "wrongpassword123", "new_password": "newlongpassword1"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert "error=wrong_password" in resp.headers["location"]


def test_settings_password_change_too_short(client, db_path, auth_cookies):
    _, cookies = auth_cookies(email="pwshort@example.com")
    resp = client.post(
        "/settings/password",
        data={"current_password": "supersecretpass1", "new_password": "short"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert "error=password_too_short" in resp.headers["location"]


def test_settings_delete_account_success(client, db_path, auth_cookies):
    user_id, cookies = auth_cookies(email="delete@example.com")
    resp = client.post(
        "/settings/delete",
        data={"confirm_email": "delete@example.com"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    assert get_user_by_email(db_path, "delete@example.com") is None


def test_settings_delete_account_email_mismatch(client, db_path, auth_cookies):
    _, cookies = auth_cookies(email="nodelete@example.com")
    resp = client.post(
        "/settings/delete",
        data={"confirm_email": "wrong@example.com"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert "error=email_mismatch" in resp.headers["location"]


def test_settings_delete_invalidates_feed(client, db_path, auth_cookies):
    user_id, cookies = auth_cookies(email="delfeed@example.com")
    token = create_feed_token(db_path, user_id)
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    client.post("/settings/delete", data={"confirm_email": "delfeed@example.com"}, cookies=cookies)
    resp = client.get(f"/feed/{token}/weather.ics")
    assert resp.status_code == 404


def test_dashboard_redirects_to_settings(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 301
    assert resp.headers["location"] == "/settings"


def test_impressum_returns_200(client):
    resp = client.get("/impressum")
    assert resp.status_code == 200


def test_privacy_returns_200(client):
    resp = client.get("/privacy")
    assert resp.status_code == 200
    assert "Privacy Policy" in resp.text


def test_terms_returns_200(client):
    resp = client.get("/terms")
    assert resp.status_code == 200
    assert "Terms of Service" in resp.text


# --- Connect, feedback, geocode routes ---

def test_connect_page_redirects_to_settings(client, db_path, auth_cookies):
    _, cookies = auth_cookies(email="connect@example.com")
    resp = client.get("/connect", cookies=cookies)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings?tab=reconnect"


def test_connect_page_from_setup_returns_200(client, db_path, auth_cookies):
    _, cookies = auth_cookies(email="connect2@example.com")
    resp = client.get("/connect?from=setup", cookies=cookies)
    assert resp.status_code == 200


def test_connect_page_shows_recommended_badge_when_not_connected(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    _, cookies = auth_cookies(email="connect_badge@example.com")
    resp = client.get("/connect?from=setup", cookies=cookies)
    assert resp.status_code == 200
    assert b"Recommended" in resp.content


def test_connect_page_hides_recommended_badge_when_connected(client, db_path, monkeypatch, auth_cookies):
    from unittest.mock import MagicMock
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    user_id, cookies = auth_cookies(email="connect_badge2@example.com")
    cred = MagicMock()
    cred.token = "tok"
    cred.refresh_token = "ref"
    cred.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    store_google_tokens(db_path, user_id, cred, "cal123")
    resp = client.get("/connect?from=setup", cookies=cookies)
    assert resp.status_code == 200
    assert b"Recommended" not in resp.content


def test_connect_page_requires_auth(client):
    resp = client.get("/connect")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_feedback_get_redirects_to_mailto():
    """GET /feedback returns 303 redirect to mailto:hello@weathercal.app."""
    import asyncio
    from src.web.app import app

    async def _call():
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/feedback",
            "query_string": b"",
            "headers": [],
            "root_path": "",
        }
        status_code = None
        headers = {}

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            nonlocal status_code, headers
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = {k.decode(): v.decode() for k, v in message.get("headers", [])}

        await app(scope, receive, send)
        return status_code, headers

    status_code, headers = asyncio.get_event_loop().run_until_complete(_call())
    assert status_code == 303
    assert headers["location"] == "mailto:hello@weathercal.app"


def test_geocode_short_query_returns_empty(client):
    resp = client.get("/geocode?q=ab")
    assert resp.status_code == 200
    assert resp.json() == []


def test_setup_does_not_trigger_welcome_email_on_location_change(client, db_path, monkeypatch, auth_cookies):
    """Welcome email is NOT sent when user already has a location."""
    calls = []
    monkeypatch.setenv("ENABLE_WELCOME_EMAIL", "true")
    monkeypatch.setattr(web_app, "send_welcome_email", lambda *a, **kw: calls.append(a))

    user_id, cookies = auth_cookies(email="existing@example.com")
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")

    client.post(
        "/setup",
        data={
            "location": "Berlin",
            "lat": "52.520",
            "lon": "13.405",
            "timezone": "Europe/Berlin",
        },
        cookies=cookies,
    )
    assert len(calls) == 0


# --- Maintenance mode ---

def test_maintenance_mode_returns_503(client, tmp_path, monkeypatch):
    flag = tmp_path / "maintenance.flag"
    flag.touch()
    monkeypatch.setattr(web_app, "MAINTENANCE_FLAG", flag)
    resp = client.get("/")
    assert resp.status_code == 503
    assert "Warming up" in resp.text


def test_maintenance_mode_off_returns_200(client, tmp_path, monkeypatch):
    flag = tmp_path / "maintenance.flag"
    monkeypatch.setattr(web_app, "MAINTENANCE_FLAG", flag)
    resp = client.get("/")
    assert resp.status_code == 200


# --- Account deletion cleans up all related data ---

def test_delete_account_removes_all_related_data(db_path):
    user_id = create_user(db_path, "cleanup@example.com", "supersecretpass1")
    token = create_feed_token(db_path, user_id)
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    upsert_user_preferences(db_path, user_id, **DEFAULT_PREFS)
    save_feedback(db_path, user_id, "cleanup@example.com", "", "Munich", "", "Nice!", "", "", "", "", "")
    log_feed_poll(db_path, token, "TestAgent/1.0")

    delete_user_account(db_path, user_id)

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM user_locations WHERE user_id = ?", (user_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM user_preferences WHERE user_id = ?", (user_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM feedback WHERE user_id = ?", (user_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM feed_tokens WHERE user_id = ?", (user_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM poll_log WHERE token = ?", (token,)).fetchone()[0] == 0
    # User row still exists but is_active = 0
    user = conn.execute("SELECT is_active FROM users WHERE id = ?", (user_id,)).fetchone()
    assert user[0] == 0
    conn.close()


# --- Data export ---

def test_export_user_data_returns_all_sections(db_path):
    user_id = create_user(db_path, "export@example.com", "supersecretpass1")
    token = create_feed_token(db_path, user_id)
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    upsert_user_preferences(db_path, user_id, **DEFAULT_PREFS)
    save_feedback(db_path, user_id, "export@example.com", "", "Munich", "", "Great!", "", "", "", "", "")
    log_feed_poll(db_path, token, "TestAgent/1.0")

    data = export_user_data(db_path, user_id)

    assert data["account"]["email"] == "export@example.com"
    assert len(data["locations"]) == 1
    assert data["locations"][0]["location"] == "Munich"
    assert data["preferences"]["cold_threshold"] == 3.0
    assert len(data["feed_tokens"]) == 1
    assert len(data["poll_logs"]) == 1
    assert "ip_address" not in data["poll_logs"][0]
    assert len(data["feedback"]) == 1
    assert data["feedback"][0]["description"] == "Great!"


def test_export_endpoint_returns_json_download(client, db_path, auth_cookies):
    user_id, cookies = auth_cookies(email="exportroute@example.com")
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")

    resp = client.get("/settings/export", cookies=cookies)

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    assert "attachment" in resp.headers["content-disposition"]
    assert "weathercal-data.json" in resp.headers["content-disposition"]
    body = resp.json()
    assert "account" in body
    assert "locations" in body
    assert body["account"]["email"] == "exportroute@example.com"


def test_export_endpoint_requires_auth(client):
    resp = client.get("/settings/export")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


# --- Google OAuth routes ---

def test_google_auth_start_requires_login(client):
    resp = client.get("/auth/google")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_google_auth_start_redirects_to_google(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    _, cookies = auth_cookies(email="gauth@example.com")

    from unittest.mock import MagicMock, patch
    mock_flow = MagicMock()
    mock_flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth?test=1", "state")

    with patch("src.web.app.get_oauth_flow", return_value=mock_flow):
        with patch("src.web.app.google_oauth_enabled", return_value=True):
            resp = client.get("/auth/google", cookies=cookies)

    assert resp.status_code == 303
    assert "accounts.google.com" in resp.headers["location"]


def test_google_auth_callback_stores_tokens(client, db_path, monkeypatch, auth_cookies):
    from unittest.mock import MagicMock, patch
    from datetime import datetime, timedelta, timezone
    from jose import jwt as _jwt
    from src.web.auth import SECRET_KEY

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")

    user_id, cookies = auth_cookies(email="gcallback@example.com")

    state = _jwt.encode(
        {"user_id": user_id, "purpose": "google_oauth"},
        SECRET_KEY,
        algorithm="HS256",
    )

    mock_flow = MagicMock()
    mock_creds = MagicMock()
    mock_creds.token = "access_token_123"
    mock_creds.refresh_token = "refresh_token_123"
    mock_creds.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    mock_flow.credentials = mock_creds

    mock_service = MagicMock()
    mock_service.calendars().insert().execute.return_value = {"id": "new_cal@group.calendar.google.com"}

    with patch("src.web.app.get_oauth_flow", return_value=mock_flow), \
         patch("src.web.app.build_google_service", return_value=mock_service), \
         patch("src.web.app.create_weathercal_calendar", return_value="new_cal@group.calendar.google.com"), \
         patch("src.web.app._google_push_initial"):
        resp = client.get(f"/auth/google/callback?code=test_code&state={state}", cookies=cookies)

    assert resp.status_code == 303
    assert "success=google_connected" in resp.headers["location"]

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT * FROM google_tokens WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    assert row is not None


def test_google_auth_disconnect_requires_login(client):
    resp = client.post("/auth/google/disconnect")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_google_auth_disconnect_deletes_tokens(client, db_path, monkeypatch, auth_cookies):
    from unittest.mock import MagicMock, patch
    from datetime import datetime, timedelta, timezone

    user_id, cookies = auth_cookies(email="gdiscon@example.com")
    cred = MagicMock()
    cred.token = "tok"
    cred.refresh_token = "ref"
    cred.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    store_google_tokens(db_path, user_id, cred, "cal123")

    with patch("src.integrations.google_push.get_google_credentials") as mock_get_creds:
        mock_get_creds.return_value = None
        resp = client.post("/auth/google/disconnect", cookies=cookies)

    assert resp.status_code == 303
    assert "success=google_disconnected" in resp.headers["location"]

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT * FROM google_tokens WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    assert row is None


def test_settings_shows_google_connect_when_enabled(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    user_id, cookies = auth_cookies(email="gshow@example.com")
    create_feed_token(db_path, user_id)
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    resp = client.get("/settings", cookies=cookies)
    assert resp.status_code == 200
    assert b"Connect with Google Calendar" in resp.content
    assert b"Recommended" in resp.content


def test_settings_shows_connected_status(client, db_path, monkeypatch, auth_cookies):
    from unittest.mock import MagicMock
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-secret")
    user_id, cookies = auth_cookies(email="gconn@example.com")
    create_feed_token(db_path, user_id)
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    cred = MagicMock()
    cred.token = "tok"
    cred.refresh_token = "ref"
    cred.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    store_google_tokens(db_path, user_id, cred, "cal123")

    resp = client.get("/settings", cookies=cookies)
    assert resp.status_code == 200
    assert b"Disconnect Google Calendar" in resp.content
    assert b"Recommended" not in resp.content


def test_settings_hides_google_when_not_configured(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    user_id, cookies = auth_cookies(email="ghide@example.com")
    create_feed_token(db_path, user_id)
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    resp = client.get("/settings", cookies=cookies)
    assert resp.status_code == 200
    assert b"Connect with Google Calendar" not in resp.content


def test_delete_account_cleans_google_tokens(db_path):
    from unittest.mock import MagicMock
    from datetime import datetime, timedelta, timezone

    user_id = create_user(db_path, "gdelete@example.com", "supersecretpass1")
    create_feed_token(db_path, user_id)
    cred = MagicMock()
    cred.token = "tok"
    cred.refresh_token = "ref"
    cred.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    store_google_tokens(db_path, user_id, cred, "cal123")

    delete_user_account(db_path, user_id)

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT * FROM google_tokens WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    assert row is None


# --- resolve_prefs ---


def test_resolve_prefs_none_returns_defaults():
    from src.constants import DEFAULT_PREFS
    from src.web.db import resolve_prefs
    result = resolve_prefs(None)
    assert result == DEFAULT_PREFS
    # Ensure it's a copy, not the same object
    assert result is not DEFAULT_PREFS


def test_resolve_prefs_fills_null_columns(db_path):
    """A row with NULL columns should fall back to defaults for those keys."""
    from src.constants import DEFAULT_PREFS
    from src.web.db import resolve_prefs
    # Simulate a sqlite3.Row with some NULL values
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO user_preferences (user_id, cold_threshold, show_allday_events) VALUES (?, ?, ?)",
        (999, 5.0, None),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM user_preferences WHERE user_id = 999").fetchone()
    conn.close()

    result = resolve_prefs(row)
    # NULL show_allday_events should be filled from default (1)
    assert result["show_allday_events"] == DEFAULT_PREFS["show_allday_events"]
    # Explicit value should be preserved
    assert result["cold_threshold"] == 5.0


def test_resolve_prefs_preserves_zero_values(db_path):
    """0-valued prefs (like show_allday_events=0) must survive the merge."""
    from src.web.db import resolve_prefs
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO user_preferences (user_id, show_allday_events, warn_rain) VALUES (?, ?, ?)",
        (998, 0, 0),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM user_preferences WHERE user_id = 998").fetchone()
    conn.close()

    result = resolve_prefs(row)
    assert result["show_allday_events"] == 0
    assert result["warn_rain"] == 0


def test_settings_post_triggers_gcal_push_when_connected(client, db_path, monkeypatch, auth_cookies):
    from unittest.mock import MagicMock, patch
    from datetime import datetime, timedelta, timezone

    user_id, cookies = auth_cookies(email="gcalpush@example.com")
    create_feed_token(db_path, user_id)
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")

    # Store Google tokens to make user "connected"
    cred = MagicMock()
    cred.token = "tok"
    cred.refresh_token = "ref"
    cred.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    store_google_tokens(db_path, user_id, cred, "cal123")

    with patch("src.web.app._google_push_initial") as mock_push:
        resp = client.post("/settings", data={"cold_threshold": "3.0"}, cookies=cookies)

    assert resp.status_code == 303
    mock_push.assert_called_once_with(db_path, user_id)


def test_settings_post_no_gcal_push_when_not_connected(client, db_path, auth_cookies):
    user_id, cookies = auth_cookies(email="nogcal@example.com")
    create_feed_token(db_path, user_id)
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")

    from unittest.mock import patch
    with patch("src.web.app._google_push_initial") as mock_push:
        resp = client.post("/settings", data={"cold_threshold": "3.0"}, cookies=cookies)

    assert resp.status_code == 303
    mock_push.assert_not_called()


# --- Landing page ---

def test_landing_returns_200_with_brand(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "WeatherCal" in resp.text
    assert "\U0001f324" in resp.text  # 🌤️


def test_landing_contains_sections(client):
    resp = client.get("/")
    assert "How it works" in resp.text
    assert "Questions?" in resp.text


def test_landing_unauthenticated_cta_links_signup(client):
    resp = client.get("/")
    assert "/signup" in resp.text
    assert "Get started" in resp.text


def test_landing_authenticated_cta_links_settings(client, auth_cookies):
    _, cookies = auth_cookies(email="landing@example.com")
    resp = client.get("/", cookies=cookies)
    assert "/settings" in resp.text
    assert "Go to settings" in resp.text


def test_static_files_served(client):
    resp = client.get("/static/screenshots/.gitkeep")
    assert resp.status_code == 200


# --- UTM tracking ---


def test_signup_with_utm_params_stores_them(client, db_path):
    resp = client.post(
        "/signup",
        data={
            "email": "utm@example.com",
            "password": "supersecretpass1",
            "utm_source": "twitter",
            "utm_medium": "social",
            "utm_campaign": "launch",
        },
    )
    assert resp.status_code == 303
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT utm_source, utm_medium, utm_campaign FROM users WHERE email = ?", ("utm@example.com",)).fetchone()
    conn.close()
    assert row["utm_source"] == "twitter"
    assert row["utm_medium"] == "social"
    assert row["utm_campaign"] == "launch"


def test_signup_without_utm_params_still_works(client, db_path):
    resp = client.post(
        "/signup",
        data={"email": "noutm@example.com", "password": "supersecretpass1"},
    )
    assert resp.status_code == 303
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT utm_source FROM users WHERE email = ?", ("noutm@example.com",)).fetchone()
    conn.close()
    assert row["utm_source"] is None


def test_signup_get_passes_utm_to_template(client):
    resp = client.get("/signup?utm_source=hn&utm_medium=link&utm_campaign=launch")
    assert resp.status_code == 200
    assert 'value="hn"' in resp.text
    assert 'value="link"' in resp.text
    assert 'value="launch"' in resp.text


# --- Funnel events ---


def test_signup_logs_funnel_event(client, db_path):
    client.post("/signup", data={"email": "funnel@example.com", "password": "supersecretpass1"})
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT event_name FROM funnel_events WHERE user_id = (SELECT id FROM users WHERE email = ?)",
        ("funnel@example.com",),
    ).fetchone()
    conn.close()
    assert row[0] == "signup_completed"


def test_setup_logs_location_set_funnel_event(client, db_path, auth_cookies):
    user_id, cookies = auth_cookies(email="funnelsetup@example.com")
    create_feed_token(db_path, user_id)
    client.post(
        "/setup",
        data={"location": "Munich", "lat": "48.137", "lon": "11.576", "timezone": "Europe/Berlin"},
        cookies=cookies,
    )
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT event_name FROM funnel_events WHERE user_id = ? AND event_name = 'location_set'",
        (user_id,),
    ).fetchone()
    conn.close()
    assert row is not None


def test_feed_poll_logs_feed_subscribed_once(client, db_path, auth_cookies, make_forecast):
    user_id, cookies = auth_cookies(email="feedfunnel@example.com")
    token = create_feed_token(db_path, user_id)
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    store = ForecastStore(db_path=db_path)
    store.upsert_forecast(make_forecast())
    # First poll → should log feed_subscribed
    client.get(f"/feed/{token}/weather.ics")
    # Second poll → should NOT log again
    client.get(f"/feed/{token}/weather.ics")
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT * FROM funnel_events WHERE user_id = ? AND event_name = 'feed_subscribed'",
        (user_id,),
    ).fetchall()
    conn.close()
    assert len(rows) == 1


# --- Sitemap and robots.txt ---


def test_sitemap_returns_valid_xml(client):
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    assert "<urlset" in resp.text
    assert "https://weathercal.app/" in resp.text
    assert "https://weathercal.app/signup" in resp.text
    assert "https://weathercal.app/privacy" in resp.text


def test_robots_txt_returns_expected_content(client):
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "User-agent: *" in resp.text
    assert "Sitemap: https://weathercal.app/sitemap.xml" in resp.text


# --- Admin dashboard source column ---


def test_admin_shows_utm_source(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    user_id, cookies = auth_cookies(email="admin@example.com")
    # Create a user with utm_source
    from src.web.db import log_funnel_event
    uid2 = create_user(db_path, "tracked@example.com", "password123456", utm_source="producthunt")
    set_user_location(db_path, uid2, "Berlin", 52.52, 13.405, "Europe/Berlin")
    create_feed_token(db_path, uid2)
    resp = client.get("/admin", cookies=cookies)
    assert resp.status_code == 200
    assert "producthunt" in resp.text
    assert "Source" in resp.text


# --- OG tags ---


def test_google_auth_callback_logs_google_connected_funnel_event(client, db_path, monkeypatch, auth_cookies):
    from unittest.mock import MagicMock, patch
    from datetime import datetime, timedelta, timezone
    from jose import jwt as _jwt
    from src.web.auth import SECRET_KEY

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")

    user_id, cookies = auth_cookies(email="gcfunnel@example.com")

    state = _jwt.encode(
        {"user_id": user_id, "purpose": "google_oauth"},
        SECRET_KEY,
        algorithm="HS256",
    )

    mock_flow = MagicMock()
    mock_creds = MagicMock()
    mock_creds.token = "access_token_123"
    mock_creds.refresh_token = "refresh_token_123"
    mock_creds.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    mock_flow.credentials = mock_creds

    with patch("src.web.app.get_oauth_flow", return_value=mock_flow), \
         patch("src.web.app.build_google_service", return_value=MagicMock()), \
         patch("src.web.app.create_weathercal_calendar", return_value="cal@group.calendar.google.com"), \
         patch("src.web.app._google_push_initial"):
        client.get(f"/auth/google/callback?code=test_code&state={state}", cookies=cookies)

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT event_name FROM funnel_events WHERE user_id = ? AND event_name = 'google_connected'",
        (user_id,),
    ).fetchone()
    conn.close()
    assert row is not None


# --- Signup validation preserves UTM ---


def test_signup_validation_error_preserves_utm_params(client):
    resp = client.post(
        "/signup",
        data={
            "email": "short@example.com",
            "password": "short",
            "utm_source": "twitter",
            "utm_medium": "social",
            "utm_campaign": "launch",
        },
    )
    assert resp.status_code == 422
    assert 'value="twitter"' in resp.text
    assert 'value="social"' in resp.text
    assert 'value="launch"' in resp.text


# --- OG tags ---


def test_landing_has_og_tags(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'og:title' in resp.text
    assert 'og:description' in resp.text
    assert 'og:image' in resp.text
    assert 'twitter:card' in resp.text


# --- Admin analytics extensions ---


def test_admin_shows_timeseries_section(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    _, cookies = auth_cookies(email="admin@example.com")
    resp = client.get("/admin", cookies=cookies)
    assert resp.status_code == 200
    assert "Funnel over time" in resp.text
    assert "30 days" in resp.text


def test_admin_accepts_days_param(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    _, cookies = auth_cookies(email="admin@example.com")
    resp = client.get("/admin?days=7", cookies=cookies)
    assert resp.status_code == 200
    assert "Funnel over time" in resp.text


def test_admin_shows_source_breakdown(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    uid, cookies = auth_cookies(email="admin@example.com")
    from src.web.db import log_funnel_event
    log_funnel_event(db_path, uid, "signup_completed")
    resp = client.get("/admin", cookies=cookies)
    assert resp.status_code == 200
    assert "Funnel by source" in resp.text


def test_admin_shows_page_view_cards(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    _, cookies = auth_cookies(email="admin@example.com")
    # Visit landing to generate a page view
    client.get("/")
    resp = client.get("/admin", cookies=cookies)
    assert resp.status_code == 200
    assert "Landing views" in resp.text
    assert "Signup views" in resp.text


def test_landing_increments_page_views(client, db_path):
    client.get("/")
    client.get("/")
    from src.web.db import get_page_view_stats
    stats = get_page_view_stats(db_path)
    assert stats["today"].get("/", 0) >= 2


def test_signup_increments_page_views(client, db_path):
    client.get("/signup")
    from src.web.db import get_page_view_stats
    stats = get_page_view_stats(db_path)
    assert stats["today"].get("/signup", 0) >= 1


def test_csv_export_requires_auth(client):
    resp = client.get("/admin/export.csv")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_csv_export_forbidden_for_non_admin(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    _, cookies = auth_cookies(email="nonadmin@example.com")
    resp = client.get("/admin/export.csv", cookies=cookies)
    assert resp.status_code == 403


def test_csv_export_returns_csv_with_data(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    _, cookies = auth_cookies(email="admin@example.com")
    # Create a second user so there's data to export
    uid2 = create_user(db_path, "csvuser@example.com", "password123456", utm_source="reddit")
    set_user_location(db_path, uid2, "Berlin", 52.52, 13.405, "Europe/Berlin")
    create_feed_token(db_path, uid2)
    resp = client.get("/admin/export.csv", cookies=cookies)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "Content-Disposition" in resp.headers
    lines = resp.text.strip().split("\n")
    assert "Email" in lines[0]
    assert "Location" in lines[0]
    assert len(lines) >= 3  # header + at least 2 users


def test_admin_shows_export_csv_link(client, db_path, monkeypatch, auth_cookies):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    _, cookies = auth_cookies(email="admin@example.com")
    resp = client.get("/admin", cookies=cookies)
    assert resp.status_code == 200
    assert "/admin/export.csv" in resp.text


# --- Dual-calendar: feed gating when Google is connected ---

def test_feed_returns_info_ics_when_google_connected(client, db_path, auth_cookies):
    from datetime import datetime as _dt, timedelta, timezone as _tz
    from unittest.mock import MagicMock

    user_id, _ = auth_cookies()
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    token = create_feed_token(db_path, user_id)

    store = ForecastStore(db_path=db_path)
    store.upsert_forecast(Forecast(
        date="2099-01-01", location="Munich", high=10, low=2,
        summary="Test", description="Test",
        times=["2099-01-01T12:00"], temps=[10], codes=[1], rain=[0], winds=[5],
        timezone="Europe/Berlin",
    ))

    # Connect Google Calendar
    cred = MagicMock()
    cred.token = "tok"
    cred.refresh_token = "ref"
    cred.expiry = _dt.now(_tz.utc) + timedelta(hours=1)
    store_google_tokens(db_path, user_id, cred, "cal123")

    resp = client.get(f"/feed/{token}/weather.ics")
    assert resp.status_code == 200
    assert "text/calendar" in resp.headers["content-type"]
    assert b"google-active@weathercal.app" in resp.content
    assert b"Google Calendar" in resp.content


def test_feed_returns_weather_when_google_not_connected(client, db_path, auth_cookies):
    user_id, _ = auth_cookies()
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    token = create_feed_token(db_path, user_id)

    store = ForecastStore(db_path=db_path)
    store.upsert_forecast(Forecast(
        date="2099-01-01", location="Munich", high=10, low=2,
        summary="Test", description="Test",
        times=["2099-01-01T12:00"], temps=[10], codes=[1], rain=[0], winds=[5],
        timezone="Europe/Berlin",
    ))

    resp = client.get(f"/feed/{token}/weather.ics")
    assert resp.status_code == 200
    assert b"google-active@weathercal.app" not in resp.content


# --- Dual-calendar: settings UI hides subscription when Google connected ---

def test_settings_hides_subscription_when_google_connected(client, db_path, auth_cookies, monkeypatch):
    from datetime import datetime as _dt, timedelta, timezone as _tz
    from unittest.mock import MagicMock

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "fake-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "fake-secret")

    user_id, cookies = auth_cookies()
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    create_feed_token(db_path, user_id)

    # Connect Google
    cred = MagicMock()
    cred.token = "tok"
    cred.refresh_token = "ref"
    cred.expiry = _dt.now(_tz.utc) + timedelta(hours=1)
    store_google_tokens(db_path, user_id, cred, "cal123")

    resp = client.get("/settings", cookies=cookies)
    assert resp.status_code == 200
    assert "Subscribe with a calendar link" not in resp.text
    assert "Disconnect Google Calendar" in resp.text


def test_settings_shows_subscription_when_google_not_connected(client, db_path, auth_cookies, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "fake-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "fake-secret")

    user_id, cookies = auth_cookies()
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    create_feed_token(db_path, user_id)

    resp = client.get("/settings", cookies=cookies)
    assert resp.status_code == 200
    assert "Subscribe with a calendar link" in resp.text
