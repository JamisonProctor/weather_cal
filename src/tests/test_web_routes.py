import pytest
from fastapi.testclient import TestClient

import src.web.app as web_app
from src.models.forecast import Forecast
from src.services.forecast_store import ForecastStore
from src.web.auth import create_session_token
from src.web.db import (
    create_feed_token,
    create_feedback_table,
    create_user,
    create_user_location,
    create_user_preferences_table,
    get_user_preferences,
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
    create_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
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
    create_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
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
