"""Shared test fixtures for the entire test suite."""

import sqlite3
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from icalendar import Calendar

from src.events.db import create_event_tables
from src.events.sources import create_source_tables
from src.integrations.google_push import create_google_tokens_table
from src.models.forecast import Forecast
from src.services.forecast_store import ForecastStore
from src.web.auth import create_session_token
from src.web.db import (
    create_feedback_table,
    create_user,
    create_user_preferences_table,
)


def future_iso(days=7):
    """ISO timestamp N days ahead."""
    return (datetime.now() + timedelta(days=days)).isoformat()


def past_iso(days=7):
    """ISO timestamp N days ago."""
    return (datetime.now() - timedelta(days=days)).isoformat()


@pytest.fixture
def db_path(tmp_path):
    """Create a temp SQLite DB with ALL tables (maximal approach)."""
    path = str(tmp_path / "test.db")
    ForecastStore(db_path=path)
    create_feedback_table(path)
    create_user_preferences_table(path)
    create_event_tables(path)
    create_source_tables(path)
    create_google_tokens_table(path)
    return path


@pytest.fixture
def client(db_path, monkeypatch):
    """FastAPI TestClient with monkeypatched DB_PATH."""
    import src.web.app as web_app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(web_app, "DB_PATH", db_path)
    monkeypatch.setattr(web_app, "_initial_forecast_fetch", lambda *a, **kw: None)
    return TestClient(web_app.app, follow_redirects=False)


@pytest.fixture
def auth_cookies(client, db_path):
    """Factory fixture: creates user, sets session cookie on client, returns (user_id, client)."""
    def _make(email="test@example.com", password="supersecretpass1"):
        user_id = create_user(db_path, email, password)
        token = create_session_token(user_id)
        client.cookies.set("session", token)
        return user_id, client
    return _make


@pytest.fixture
def make_forecast():
    """Factory fixture: returns callable with Forecast defaults + **kwargs."""
    def _make(date="2026-03-10", location="Munich", timezone="Europe/Berlin", **kwargs):
        defaults = dict(
            date=date,
            location=location,
            high=15,
            low=5,
            summary="AM☀️10° / PM⛅15°",
            description="Nice day",
            times=[],
            temps=[],
            codes=[],
            rain=[],
            precipitation=[],
            winds=[],
            timezone=timezone,
        )
        defaults.update(kwargs)
        return Forecast(**defaults)
    return _make


@pytest.fixture
def parse_ics_events():
    """Factory fixture: returns callable (ics_bytes) -> list[VEVENT]."""
    def _parse(ics_bytes):
        cal = Calendar.from_ical(ics_bytes)
        return [c for c in cal.walk() if c.name == "VEVENT"]
    return _parse


@pytest.fixture
def insert_event(db_path):
    """Factory fixture: insert event into SQLite with defaults + **overrides."""
    def _insert(**overrides):
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
    return _insert
