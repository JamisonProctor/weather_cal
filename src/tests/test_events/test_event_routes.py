import sqlite3
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import src.web.app as web_app
from src.events.db import create_event_tables
from src.services.forecast_store import ForecastStore
from src.web.db import create_feed_token, create_feedback_table, create_user, create_user_preferences_table


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    ForecastStore(db_path=path)
    create_feedback_table(path)
    create_user_preferences_table(path)
    create_event_tables(path)
    return path


@pytest.fixture
def client(db_path, monkeypatch):
    monkeypatch.setattr(web_app, "DB_PATH", db_path)
    monkeypatch.setattr(web_app, "_initial_forecast_fetch", lambda *a, **kw: None)
    return TestClient(web_app.app, follow_redirects=False)


def _insert_event(db_path, **overrides):
    future = datetime.now() + timedelta(days=7)
    defaults = dict(
        id=str(uuid.uuid4()),
        title="Test Event",
        start_time=future.isoformat(),
        end_time=(future + timedelta(hours=2)).isoformat(),
        location="Munich",
        description="A test event",
        source_url="https://example.com/event",
        external_key=str(uuid.uuid4()),
        category="concert",
        is_paid=0,
        is_calendar_candidate=1,
        created_at=datetime.now().isoformat(),
    )
    defaults.update(overrides)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO events
           (id, title, start_time, end_time, location, description,
            source_url, external_key, category, is_paid, is_calendar_candidate, created_at)
           VALUES (:id, :title, :start_time, :end_time, :location, :description,
                   :source_url, :external_key, :category, :is_paid, :is_calendar_candidate, :created_at)""",
        defaults,
    )
    conn.commit()
    conn.close()


# --- /events.ics ---

def test_events_ics_returns_200(client):
    resp = client.get("/events.ics")
    assert resp.status_code == 200
    assert "text/calendar" in resp.headers["content-type"]


def test_events_ics_empty_db(client):
    resp = client.get("/events.ics")
    assert resp.status_code == 200
    assert b"VCALENDAR" in resp.content


def test_events_ics_contains_event(client, db_path):
    _insert_event(db_path, title="ICS Route Test Event")
    resp = client.get("/events.ics")
    assert resp.status_code == 200
    assert b"ICS Route Test Event" in resp.content


# --- /events/free.ics ---

def test_events_free_ics_returns_200(client):
    resp = client.get("/events/free.ics")
    assert resp.status_code == 200
    assert "text/calendar" in resp.headers["content-type"]


def test_events_free_ics_excludes_paid(client, db_path):
    _insert_event(db_path, title="Free Event", is_paid=0, external_key="free1")
    _insert_event(db_path, title="Paid Event", is_paid=1, external_key="paid1")
    resp = client.get("/events/free.ics")
    assert b"Free Event" in resp.content
    assert b"Paid Event" not in resp.content


# --- /feed/{token}/events.ics ---

def test_feed_events_ics_invalid_token(client):
    resp = client.get("/feed/invalid-token/events.ics")
    assert resp.status_code == 404


def test_feed_events_ics_valid_token(client, db_path):
    user_id = create_user(db_path, "test@example.com", "supersecretpass1")
    create_feed_token(db_path, user_id)
    from src.web.db import get_feed_token_by_user
    token = get_feed_token_by_user(db_path, user_id)
    _insert_event(db_path, title="User Event")
    resp = client.get(f"/feed/{token}/events.ics")
    assert resp.status_code == 200
    assert b"User Event" in resp.content


def test_events_ics_excludes_past_events(client, db_path):
    past = datetime.now() - timedelta(days=7)
    _insert_event(db_path, title="Past Event", start_time=past.isoformat(),
                  end_time=(past + timedelta(hours=2)).isoformat(), external_key="past1")
    _insert_event(db_path, title="Future Event", external_key="future1")
    resp = client.get("/events.ics")
    assert b"Future Event" in resp.content
    assert b"Past Event" not in resp.content


# --- /health ---

def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# --- Content-Disposition headers ---

def test_events_ics_content_disposition(client):
    resp = client.get("/events.ics")
    assert 'filename="events.ics"' in resp.headers["content-disposition"]


def test_events_free_ics_content_disposition(client):
    resp = client.get("/events/free.ics")
    assert 'filename="events.ics"' in resp.headers["content-disposition"]


def test_feed_events_ics_content_disposition(client, db_path):
    user_id = create_user(db_path, "disp@example.com", "supersecretpass1")
    create_feed_token(db_path, user_id)
    from src.web.db import get_feed_token_by_user
    token = get_feed_token_by_user(db_path, user_id)
    resp = client.get(f"/feed/{token}/events.ics")
    assert 'filename="events.ics"' in resp.headers["content-disposition"]


# --- Weather feed still works alongside events ---

def test_weather_feed_works_alongside_events(client, db_path):
    from src.models.forecast import Forecast
    from src.web.db import set_user_location, get_feed_token_by_user
    user_id = create_user(db_path, "weather@example.com", "supersecretpass1")
    set_user_location(db_path, user_id, "Munich, Germany", 48.137, 11.576, "Europe/Berlin")
    create_feed_token(db_path, user_id)
    token = get_feed_token_by_user(db_path, user_id)

    from src.services.forecast_store import ForecastStore
    store = ForecastStore(db_path=db_path)
    store.upsert_forecast(Forecast(
        date="2099-01-01", location="Munich, Germany",
        high=10, low=2, summary="Test", description="Test forecast",
        times=["2099-01-01T12:00"], temps=[10], codes=[1], rain=[0], winds=[5],
        timezone="Europe/Berlin",
    ))
    _insert_event(db_path, title="Coexist Event")

    weather_resp = client.get(f"/feed/{token}/weather.ics")
    assert weather_resp.status_code == 200
    assert b"VCALENDAR" in weather_resp.content

    events_resp = client.get(f"/feed/{token}/events.ics")
    assert events_resp.status_code == 200
    assert b"Coexist Event" in events_resp.content


# --- Empty events DB with valid token ---

def test_feed_events_ics_empty_db(client, db_path):
    user_id = create_user(db_path, "empty@example.com", "supersecretpass1")
    create_feed_token(db_path, user_id)
    from src.web.db import get_feed_token_by_user
    token = get_feed_token_by_user(db_path, user_id)
    resp = client.get(f"/feed/{token}/events.ics")
    assert resp.status_code == 200
    assert b"VCALENDAR" in resp.content
