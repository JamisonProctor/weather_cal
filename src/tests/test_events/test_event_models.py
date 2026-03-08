import sqlite3
import uuid

import pytest

from src.events.constants import EVENT_CATEGORIES
from src.events.db import create_event_tables
from src.events.models import Event, EventSeries
from src.services.forecast_store import ForecastStore


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_events.db")
    ForecastStore(db_path=path)
    create_event_tables(path)
    return path


# --- Dataclass tests ---


def test_event_creation():
    e = Event(
        id=str(uuid.uuid4()),
        title="Open Air Concert",
        start_time="2026-03-15T18:00:00+01:00",
        end_time="2026-03-15T21:00:00+01:00",
        location="Olympiapark",
        description="Free concert in the park",
        source_url="https://example.com/concert",
        external_key="abc123",
        category="concert",
        is_paid=False,
        is_calendar_candidate=True,
        created_at="2026-03-08T10:00:00",
    )
    assert e.title == "Open Air Concert"
    assert e.is_paid is False
    assert e.is_calendar_candidate is True
    assert e.category == "concert"


def test_event_created_at_auto_set():
    e = Event(
        id=str(uuid.uuid4()),
        title="Test",
        start_time="2026-03-15T18:00:00+01:00",
        end_time="2026-03-15T21:00:00+01:00",
    )
    assert e.created_at is not None


def test_event_series_creation():
    s = EventSeries(
        id=str(uuid.uuid4()),
        series_key="https://example.com/venue",
        detail_url="https://example.com/venue",
        title="Weekly Jazz Night",
        description="Jazz every Friday",
        venue_address="Jazzbar, Munich",
        category="concert",
        is_paid=False,
        updated_at="2026-03-08T10:00:00",
    )
    assert s.series_key == "https://example.com/venue"
    assert s.is_paid is False


def test_event_series_updated_at_auto_set():
    s = EventSeries(
        id=str(uuid.uuid4()),
        series_key="https://example.com/venue",
    )
    assert s.updated_at is not None


# --- Table creation tests ---


def test_event_tables_created(db_path):
    conn = sqlite3.connect(db_path)
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    conn.close()
    assert "events" in tables
    assert "event_series" in tables


def test_event_tables_idempotent(db_path):
    # calling again should not raise
    create_event_tables(db_path)


# --- Round-trip insert/query tests ---


def test_insert_and_query_event(db_path):
    event_id = str(uuid.uuid4())
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """INSERT INTO events
           (id, title, start_time, end_time, location, description,
            source_url, external_key, category, is_paid, is_calendar_candidate, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_id,
            "Museum Night",
            "2026-03-20T19:00:00+01:00",
            "2026-03-20T23:00:00+01:00",
            "Pinakothek",
            "Free museum entry",
            "https://example.com/museum",
            "ext_key_1",
            "museum",
            0,
            1,
            "2026-03-08T10:00:00",
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    assert row["title"] == "Museum Night"
    assert row["category"] == "museum"
    assert row["is_paid"] == 0
    assert row["is_calendar_candidate"] == 1


def test_event_external_key_unique(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO events
           (id, title, start_time, end_time, external_key, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (str(uuid.uuid4()), "Event A", "2026-03-15T10:00:00", "2026-03-15T12:00:00", "dup_key", "2026-03-08T10:00:00"),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO events
               (id, title, start_time, end_time, external_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), "Event B", "2026-03-16T10:00:00", "2026-03-16T12:00:00", "dup_key", "2026-03-08T10:00:00"),
        )
    conn.close()


def test_insert_and_query_event_series(db_path):
    series_id = str(uuid.uuid4())
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """INSERT INTO event_series
           (id, series_key, detail_url, title, description, venue_address, category, is_paid, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (series_id, "series_1", "https://example.com", "Jazz Night", "Weekly jazz", "Jazzbar", "concert", 0, "2026-03-08T10:00:00"),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM event_series WHERE id = ?", (series_id,)).fetchone()
    conn.close()
    assert row["title"] == "Jazz Night"
    assert row["series_key"] == "series_1"


def test_event_series_series_key_unique(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO event_series (id, series_key, updated_at) VALUES (?, ?, ?)""",
        (str(uuid.uuid4()), "dup_series", "2026-03-08T10:00:00"),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO event_series (id, series_key, updated_at) VALUES (?, ?, ?)""",
            (str(uuid.uuid4()), "dup_series", "2026-03-08T10:00:00"),
        )
    conn.close()


def test_event_boolean_storage(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """INSERT INTO events
           (id, title, start_time, end_time, external_key, is_paid, is_calendar_candidate, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (str(uuid.uuid4()), "Paid Event", "2026-03-15T10:00:00", "2026-03-15T12:00:00", "paid_1", 1, 0, "2026-03-08T10:00:00"),
    )
    conn.commit()
    row = conn.execute("SELECT is_paid, is_calendar_candidate FROM events WHERE external_key = ?", ("paid_1",)).fetchone()
    conn.close()
    assert row["is_paid"] == 1
    assert row["is_calendar_candidate"] == 0


# --- Constants test ---


def test_event_categories():
    assert len(EVENT_CATEGORIES) == 7
    assert "theater" in EVENT_CATEGORIES
    assert "concert" in EVENT_CATEGORIES
    assert "other" in EVENT_CATEGORIES
