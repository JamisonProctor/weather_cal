import sqlite3
from datetime import datetime, timedelta

import pytest

from src.events.db import create_event_tables
from src.events.store import store_events
from src.services.forecast_store import ForecastStore


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_store.db")
    ForecastStore(db_path=path)
    create_event_tables(path)
    return path


def _future(days=7):
    return (datetime.now() + timedelta(days=days)).isoformat()


def _past(days=7):
    return (datetime.now() - timedelta(days=days)).isoformat()


def _make_event_dict(**overrides):
    defaults = dict(
        title="Test Event",
        start_time=_future(7),
        end_time=_future(7),
        location="Munich",
        description="A test event",
        source_url="https://example.com/event",
        category="concert",
        is_paid=False,
    )
    defaults.update(overrides)
    return defaults


def test_store_events_creates_new(db_path):
    events = [_make_event_dict(source_url="https://a.com", start_time=_future(1))]
    result = store_events(db_path, events, datetime.now())
    assert result["created"] == 1
    assert result["updated"] == 0


def test_store_events_generates_external_key(db_path):
    events = [_make_event_dict(source_url="https://a.com", start_time=_future(1))]
    store_events(db_path, events, datetime.now())
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT external_key FROM events").fetchone()
    conn.close()
    assert row["external_key"] is not None
    assert len(row["external_key"]) > 10


def test_store_events_idempotent_insert(db_path):
    events = [_make_event_dict(source_url="https://a.com", start_time=_future(1))]
    r1 = store_events(db_path, events, datetime.now())
    r2 = store_events(db_path, events, datetime.now())
    assert r1["created"] == 1
    assert r2["created"] == 0
    assert r2["updated"] == 0
    # Only one row in DB
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()
    assert count == 1


def test_store_events_updates_changed_fields(db_path):
    events = [_make_event_dict(source_url="https://a.com", start_time=_future(1), title="V1")]
    store_events(db_path, events, datetime.now())
    events[0]["title"] = "V2"
    r2 = store_events(db_path, events, datetime.now())
    assert r2["updated"] == 1
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT title FROM events").fetchone()
    conn.close()
    assert row["title"] == "V2"


def test_store_events_discards_past(db_path):
    events = [_make_event_dict(source_url="https://past.com", start_time=_past(1), end_time=_past(1))]
    result = store_events(db_path, events, datetime.now())
    assert result["discarded_past"] == 1
    assert result["created"] == 0


def test_store_events_multiple(db_path):
    events = [
        _make_event_dict(source_url="https://a.com", start_time=_future(1)),
        _make_event_dict(source_url="https://b.com", start_time=_future(2)),
        _make_event_dict(source_url="https://c.com", start_time=_past(1), end_time=_past(1)),
    ]
    result = store_events(db_path, events, datetime.now())
    assert result["created"] == 2
    assert result["discarded_past"] == 1


def test_store_events_no_update_when_unchanged(db_path):
    events = [_make_event_dict(source_url="https://a.com", start_time=_future(1))]
    store_events(db_path, events, datetime.now())
    r2 = store_events(db_path, events, datetime.now())
    assert r2["updated"] == 0


def test_store_events_empty_list(db_path):
    result = store_events(db_path, [], datetime.now())
    assert result == {"created": 0, "updated": 0, "discarded_past": 0}


def test_external_key_formula(db_path):
    """Stored external_key matches sha256(source_url|start_time)."""
    import hashlib
    source_url = "https://example.com/test-key"
    start_time = _future(3)
    events = [_make_event_dict(source_url=source_url, start_time=start_time)]
    store_events(db_path, events, datetime.now())

    expected = hashlib.sha256(f"{source_url}|{start_time}".encode()).hexdigest()
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT external_key FROM events").fetchone()
    conn.close()
    assert row[0] == expected
