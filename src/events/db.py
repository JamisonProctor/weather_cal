import sqlite3
from datetime import datetime
from types import SimpleNamespace

from src.events.sources import create_source_tables


def create_event_tables(db_path: str) -> None:
    """Create events, event_series, and source tracking tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                location TEXT,
                description TEXT,
                source_url TEXT,
                external_key TEXT UNIQUE,
                category TEXT,
                is_paid INTEGER NOT NULL DEFAULT 0,
                is_calendar_candidate INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_start_time ON events (start_time)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_category ON events (category)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS event_series (
                id TEXT PRIMARY KEY,
                series_key TEXT NOT NULL UNIQUE,
                detail_url TEXT,
                title TEXT,
                description TEXT,
                venue_address TEXT,
                category TEXT,
                is_paid INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()

    # Create source tracking tables (city_profiles, event_sources, discovery_runs)
    create_source_tables(db_path)


def get_user_id_by_feed_token(db_path: str, token: str) -> int | None:
    """Return user_id for a valid feed token, or None."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """SELECT u.id FROM feed_tokens ft
               JOIN users u ON ft.user_id = u.id
               WHERE ft.token = ? AND u.is_active = 1""",
            (token,),
        ).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def get_future_events(db_path: str, free_only: bool = False) -> list:
    """Return future events as SimpleNamespace objects for ICS generation."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        now = datetime.now().isoformat()
        sql = """SELECT * FROM events
                 WHERE is_calendar_candidate = 1 AND end_time > ?"""
        params = [now]
        if free_only:
            sql += " AND is_paid = 0"
        sql += " ORDER BY start_time"
        rows = conn.execute(sql, params).fetchall()
        return [SimpleNamespace(**dict(row)) for row in rows]
    finally:
        conn.close()
