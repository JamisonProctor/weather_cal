from datetime import datetime, timedelta

import pytest

from src.web.db import create_feed_token, create_user


# --- /events.ics ---

def test_events_ics_returns_200(client):
    resp = client.get("/events.ics")
    assert resp.status_code == 200
    assert "text/calendar" in resp.headers["content-type"]


def test_events_ics_empty_db(client):
    resp = client.get("/events.ics")
    assert resp.status_code == 200
    assert b"VCALENDAR" in resp.content


def test_events_ics_contains_event(client, insert_event):
    insert_event(title="ICS Route Test Event")
    resp = client.get("/events.ics")
    assert resp.status_code == 200
    assert b"ICS Route Test Event" in resp.content


# --- /events/free.ics ---

def test_events_free_ics_returns_200(client):
    resp = client.get("/events/free.ics")
    assert resp.status_code == 200
    assert "text/calendar" in resp.headers["content-type"]


def test_events_free_ics_excludes_paid(client, insert_event):
    insert_event(title="Free Event", is_paid=0, external_key="free1")
    insert_event(title="Paid Event", is_paid=1, external_key="paid1")
    resp = client.get("/events/free.ics")
    assert b"Free Event" in resp.content
    assert b"Paid Event" not in resp.content


# --- /feed/{token}/events.ics ---

def test_feed_events_ics_invalid_token(client):
    resp = client.get("/feed/invalid-token/events.ics")
    assert resp.status_code == 404


def test_feed_events_ics_valid_token(client, db_path, insert_event):
    user_id = create_user(db_path, "test@example.com", "supersecretpass1")
    create_feed_token(db_path, user_id)
    from src.web.db import get_feed_token_by_user
    token = get_feed_token_by_user(db_path, user_id)
    insert_event(title="User Event")
    resp = client.get(f"/feed/{token}/events.ics")
    assert resp.status_code == 200
    assert b"User Event" in resp.content


def test_events_ics_excludes_past_events(client, insert_event):
    past = datetime.now() - timedelta(days=7)
    insert_event(title="Past Event", start_time=past.isoformat(),
                  end_time=(past + timedelta(hours=2)).isoformat(), external_key="past1")
    insert_event(title="Future Event", external_key="future1")
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

def test_weather_feed_works_alongside_events(client, db_path, insert_event):
    from src.models.forecast import Forecast
    from src.web.db import set_user_location, get_feed_token_by_user
    user_id = create_user(db_path, "weather@example.com", "supersecretpass1")
    set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
    create_feed_token(db_path, user_id)
    token = get_feed_token_by_user(db_path, user_id)

    from src.services.forecast_store import ForecastStore
    store = ForecastStore(db_path=db_path)
    store.upsert_forecast(Forecast(
        date="2099-01-01", location="Munich",
        high=10, low=2, summary="Test", description="Test forecast",
        times=["2099-01-01T12:00"], temps=[10], codes=[1], rain=[0], winds=[5],
        timezone="Europe/Berlin",
    ))
    insert_event(title="Coexist Event")

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
