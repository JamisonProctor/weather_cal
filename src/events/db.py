import sqlite3


def create_event_tables(db_path: str) -> None:
    """Create events and event_series tables if they don't exist."""
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
