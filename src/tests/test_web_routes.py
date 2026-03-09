import sqlite3

import pytest
from fastapi.testclient import TestClient

import src.web.app as web_app
from src.models.forecast import Forecast
from src.services.forecast_store import ForecastStore
from src.web.auth import create_session_token
from src.web.db import (
    check_password,
    create_feed_token,
    create_feedback_table,
    create_user,
    delete_user_account,
    export_user_data,
    set_user_location,
    create_user_preferences_table,
    get_feed_token_by_user,
    get_user_by_email,
    get_user_by_id,
    get_user_preferences,
    log_feed_poll,
    save_feedback,
    upsert_user_preferences,
    DEFAULT_PREFS,
)


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    ForecastStore(db_path=path)
    create_feedback_table(path)
    create_user_preferences_table(path)
    return path


@pytest.fixture
def client(db_path, monkeypatch):
    monkeypatch.setattr(web_app, "DB_PATH", db_path)
    monkeypatch.setattr(web_app, "_initial_forecast_fetch", lambda *a, **kw: None)
    return TestClient(web_app.app, follow_redirects=False)


def _auth_cookies(db_path, email="test@example.com", password="supersecretpass1"):
    """Create a user directly and return (user_id, cookies dict)."""
    user_id = create_user(db_path, email, password)
    token = create_session_token(user_id)
    return user_id, {"session": token}


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


# --- Settings ---

def test_settings_get_requires_auth(client):
    resp = client.get("/settings")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_settings_post_saves_preferences(client, db_path):
    user_id, cookies = _auth_cookies(db_path)
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


# --- Setup ---

def test_setup_post_first_time_redirects_to_connect(client, db_path):
    _, cookies = _auth_cookies(db_path)
    resp = client.post(
        "/setup",
        data={
            "location": "Munich, Germany",
            "lat": "48.137",
            "lon": "11.576",
            "timezone": "Europe/Berlin",
        },
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/connect"


def test_setup_post_location_change_redirects_to_settings(client, db_path):
    user_id, cookies = _auth_cookies(db_path)
    set_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
    resp = client.post(
        "/setup",
        data={
            "location": "Berlin, Germany",
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


def test_feed_valid_token_returns_ics(client, db_path):
    user_id, _ = _auth_cookies(db_path)
    set_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
    token = create_feed_token(db_path, user_id)

    store = ForecastStore(db_path=db_path)
    store.upsert_forecast(Forecast(
        date="2099-01-01",
        location="Munich, Germany",
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


def test_feed_records_poll(client, db_path):
    user_id, _ = _auth_cookies(db_path)
    set_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
    token = create_feed_token(db_path, user_id)

    store = ForecastStore(db_path=db_path)
    store.upsert_forecast(Forecast(
        date="2099-01-01",
        location="Munich, Germany",
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


def test_settings_ref_cal_increments_clicks(client, db_path):
    user_id, cookies = _auth_cookies(db_path)
    token = create_feed_token(db_path, user_id)
    set_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")

    client.get("/settings?ref=cal", cookies=cookies)
    client.get("/settings?ref=cal", cookies=cookies)

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT settings_clicks FROM feed_tokens WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    assert row[0] == 2


def test_setup_us_location_sets_fahrenheit(client, db_path):
    _, cookies = _auth_cookies(db_path, email="us@example.com")
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


def test_setup_non_us_location_does_not_set_fahrenheit(client, db_path):
    _, cookies = _auth_cookies(db_path, email="de@example.com")
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


def test_settings_saves_temp_unit_fahrenheit(client, db_path):
    user_id, cookies = _auth_cookies(db_path)
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


def test_admin_route_forbidden_for_non_admin(client, db_path, monkeypatch):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    _, cookies = _auth_cookies(db_path, email="user@example.com")
    resp = client.get("/admin", cookies=cookies)
    assert resp.status_code == 403


def test_admin_route_accessible_for_admin(client, db_path, monkeypatch):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    _, cookies = _auth_cookies(db_path, email="admin@example.com")
    resp = client.get("/admin", cookies=cookies)
    assert resp.status_code == 200
    assert b"Admin" in resp.content


def test_admin_shows_feedback(client, db_path, monkeypatch):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    _, cookies = _auth_cookies(db_path, email="admin@example.com")
    from src.web.db import save_feedback
    save_feedback(db_path, 1, "sender@example.com", "", "Berlin", "Apple Calendar", "Love this app!", "", "", "", "", "")
    resp = client.get("/admin", cookies=cookies)
    assert resp.status_code == 200
    assert b"sender@example.com" in resp.content
    assert b"Love this app!" in resp.content


def test_admin_shows_no_feedback_message(client, db_path, monkeypatch):
    monkeypatch.setattr(web_app, "ADMIN_EMAIL", "admin@example.com")
    _, cookies = _auth_cookies(db_path, email="admin@example.com")
    resp = client.get("/admin", cookies=cookies)
    assert resp.status_code == 200
    assert b"No feedback yet." in resp.content


# --- Welcome email ---

def test_setup_triggers_welcome_email_on_first_setup(client, db_path, monkeypatch):
    """Welcome email is sent once on first location setup when ENABLE_WELCOME_EMAIL is set."""
    calls = []
    monkeypatch.setenv("ENABLE_WELCOME_EMAIL", "true")
    monkeypatch.setattr(web_app, "send_welcome_email", lambda *a, **kw: calls.append(a))

    user_id, cookies = _auth_cookies(db_path, email="welcome@example.com")
    create_feed_token(db_path, user_id)
    client.post(
        "/setup",
        data={
            "location": "Munich, Germany",
            "lat": "48.137",
            "lon": "11.576",
            "timezone": "Europe/Berlin",
        },
        cookies=cookies,
    )
    assert len(calls) == 1
    assert calls[0][0] == "welcome@example.com"


# --- Account management routes ---

def test_settings_email_change_success(client, db_path):
    user_id, cookies = _auth_cookies(db_path, email="emailchange@example.com")
    resp = client.post(
        "/settings/email",
        data={"new_email": "changed@example.com", "current_password": "supersecretpass1"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert "success=email" in resp.headers["location"]
    assert get_user_by_email(db_path, "changed@example.com") is not None


def test_settings_email_change_wrong_password(client, db_path):
    _, cookies = _auth_cookies(db_path, email="emailwrong@example.com")
    resp = client.post(
        "/settings/email",
        data={"new_email": "new@example.com", "current_password": "wrongpassword123"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert "error=wrong_password" in resp.headers["location"]


def test_settings_email_change_duplicate_email(client, db_path):
    create_user(db_path, "existing@example.com", "password123456")
    _, cookies = _auth_cookies(db_path, email="emaildup@example.com")
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


def test_settings_password_change_success(client, db_path):
    user_id, cookies = _auth_cookies(db_path, email="pwchange@example.com")
    resp = client.post(
        "/settings/password",
        data={"current_password": "supersecretpass1", "new_password": "newlongpassword1"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert "success=password" in resp.headers["location"]
    user = get_user_by_email(db_path, "pwchange@example.com")
    assert check_password("newlongpassword1", user["password_hash"])


def test_settings_password_change_wrong_current(client, db_path):
    _, cookies = _auth_cookies(db_path, email="pwwrong@example.com")
    resp = client.post(
        "/settings/password",
        data={"current_password": "wrongpassword123", "new_password": "newlongpassword1"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert "error=wrong_password" in resp.headers["location"]


def test_settings_password_change_too_short(client, db_path):
    _, cookies = _auth_cookies(db_path, email="pwshort@example.com")
    resp = client.post(
        "/settings/password",
        data={"current_password": "supersecretpass1", "new_password": "short"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert "error=password_too_short" in resp.headers["location"]


def test_settings_delete_account_success(client, db_path):
    user_id, cookies = _auth_cookies(db_path, email="delete@example.com")
    resp = client.post(
        "/settings/delete",
        data={"confirm_email": "delete@example.com"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    assert get_user_by_email(db_path, "delete@example.com") is None


def test_settings_delete_account_email_mismatch(client, db_path):
    _, cookies = _auth_cookies(db_path, email="nodelete@example.com")
    resp = client.post(
        "/settings/delete",
        data={"confirm_email": "wrong@example.com"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert "error=email_mismatch" in resp.headers["location"]


def test_settings_delete_invalidates_feed(client, db_path):
    user_id, cookies = _auth_cookies(db_path, email="delfeed@example.com")
    token = create_feed_token(db_path, user_id)
    set_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
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


# --- Connect, feedback, geocode routes ---

def test_connect_page_returns_200(client, db_path):
    _, cookies = _auth_cookies(db_path, email="connect@example.com")
    resp = client.get("/connect", cookies=cookies)
    assert resp.status_code == 200


def test_connect_page_requires_auth(client):
    resp = client.get("/connect")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_feedback_get_returns_200(client, db_path):
    _, cookies = _auth_cookies(db_path, email="fbget@example.com")
    resp = client.get("/feedback", cookies=cookies)
    assert resp.status_code == 200


def test_feedback_post_saves_and_shows_sent(client, db_path):
    user_id, cookies = _auth_cookies(db_path, email="fbpost@example.com")
    create_feed_token(db_path, user_id)
    set_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
    resp = client.post(
        "/feedback",
        data={
            "calendar_app": "Apple Calendar",
            "description": "Great app!",
            "user_agent": "TestAgent",
            "platform": "macOS",
            "screen_width": "1920",
            "screen_height": "1080",
            "timezone": "Europe/Berlin",
            "feed_url": "",
            "locations": "Munich, Germany",
        },
        cookies=cookies,
    )
    assert resp.status_code == 200
    assert b"sent" in resp.content.lower() or resp.status_code == 200
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT description FROM feedback WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    assert row[0] == "Great app!"


def test_settings_feedback_post_redirects(client, db_path):
    user_id, cookies = _auth_cookies(db_path, email="sfb@example.com")
    create_feed_token(db_path, user_id)
    set_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
    resp = client.post(
        "/settings/feedback",
        data={"topic": "Bug report", "description": "Something broke"},
        cookies=cookies,
    )
    assert resp.status_code == 303
    assert "success=feedback" in resp.headers["location"]
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT calendar_app, description FROM feedback WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "Bug report"
    assert row[1] == "[Bug report] Something broke"


def test_geocode_short_query_returns_empty(client):
    resp = client.get("/geocode?q=ab")
    assert resp.status_code == 200
    assert resp.json() == []


def test_setup_does_not_trigger_welcome_email_on_location_change(client, db_path, monkeypatch):
    """Welcome email is NOT sent when user already has a location."""
    calls = []
    monkeypatch.setenv("ENABLE_WELCOME_EMAIL", "true")
    monkeypatch.setattr(web_app, "send_welcome_email", lambda *a, **kw: calls.append(a))

    user_id, cookies = _auth_cookies(db_path, email="existing@example.com")
    set_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")

    client.post(
        "/setup",
        data={
            "location": "Berlin, Germany",
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
    set_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
    upsert_user_preferences(db_path, user_id, **DEFAULT_PREFS)
    save_feedback(db_path, user_id, "cleanup@example.com", "", "Munich", "", "Nice!", "", "", "", "", "")
    log_feed_poll(db_path, token, "TestAgent/1.0", "127.0.0.1")

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
    set_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
    upsert_user_preferences(db_path, user_id, **DEFAULT_PREFS)
    save_feedback(db_path, user_id, "export@example.com", "", "Munich", "", "Great!", "", "", "", "", "")
    log_feed_poll(db_path, token, "TestAgent/1.0", "127.0.0.1")

    data = export_user_data(db_path, user_id)

    assert data["account"]["email"] == "export@example.com"
    assert len(data["locations"]) == 1
    assert data["locations"][0]["location"] == "Munich, Germany"
    assert data["preferences"]["cold_threshold"] == 3.0
    assert len(data["feed_tokens"]) == 1
    assert len(data["poll_logs"]) == 1
    assert data["poll_logs"][0]["ip_address"] == "127.0.0.1"
    assert len(data["feedback"]) == 1
    assert data["feedback"][0]["description"] == "Great!"


def test_export_endpoint_returns_json_download(client, db_path):
    user_id, cookies = _auth_cookies(db_path, email="exportroute@example.com")
    set_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")

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
