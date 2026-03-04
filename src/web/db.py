import secrets
import sqlite3
import logging
from datetime import datetime

import bcrypt

logger = logging.getLogger(__name__)


def _conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_user(db_path: str, email: str, password: str) -> int:
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    created_at = datetime.now().isoformat()
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, password_hash, created_at),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_user_by_email(db_path: str, email: str):
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ? AND is_active = 1", (email,))
        return cur.fetchone()
    finally:
        conn.close()


def get_user_by_id(db_path: str, user_id: int):
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()


def set_user_location(
    db_path: str, user_id: int, location: str, lat: float, lon: float, timezone: str
) -> None:
    created_at = datetime.now().isoformat()
    conn = _conn(db_path)
    try:
        conn.execute("DELETE FROM user_locations WHERE user_id = ?", (user_id,))
        conn.execute(
            "INSERT INTO user_locations (user_id, location, lat, lon, timezone, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, location, lat, lon, timezone, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_locations(db_path: str, user_id: int):
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM user_locations WHERE user_id = ?", (user_id,))
        return cur.fetchall()
    finally:
        conn.close()


def create_feed_token(db_path: str, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    created_at = datetime.now().isoformat()
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO feed_tokens (user_id, token, created_at) VALUES (?, ?, ?)",
            (user_id, token, created_at),
        )
        conn.commit()
        return token
    finally:
        conn.close()


def get_feed_token_by_user(db_path: str, user_id: int):
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT token FROM feed_tokens WHERE user_id = ? LIMIT 1", (user_id,))
        row = cur.fetchone()
        return row["token"] if row else None
    finally:
        conn.close()


def get_rows_by_token(db_path: str, token: str):
    """Return user+location rows for a feed token, or [] if invalid."""
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.id, u.email, ul.location, ul.lat, ul.lon, ul.timezone
            FROM feed_tokens ft
            JOIN users u ON ft.user_id = u.id
            JOIN user_locations ul ON ul.user_id = u.id
            WHERE ft.token = ? AND u.is_active = 1
            """,
            (token,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def check_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_feedback_table(db_path: str) -> None:
    conn = _conn(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                email TEXT,
                feed_url TEXT,
                locations TEXT,
                calendar_app TEXT,
                description TEXT,
                user_agent TEXT,
                platform TEXT,
                screen_width TEXT,
                screen_height TEXT,
                timezone TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def save_feedback(
    db_path: str,
    user_id: int,
    email: str,
    feed_url: str,
    locations: str,
    calendar_app: str,
    description: str,
    user_agent: str,
    platform: str,
    screen_width: str,
    screen_height: str,
    timezone: str,
) -> None:
    created_at = datetime.now().isoformat()
    conn = _conn(db_path)
    try:
        conn.execute(
            """INSERT INTO feedback
               (user_id, email, feed_url, locations, calendar_app, description,
                user_agent, platform, screen_width, screen_height, timezone, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, email, feed_url, locations, calendar_app, description,
             user_agent, platform, screen_width, screen_height, timezone, created_at),
        )
        conn.commit()
    finally:
        conn.close()


DEFAULT_PREFS = {
    "cold_threshold": 3.0,
    "warn_in_allday": 1,
    "warn_rain": 1,
    "warn_wind": 1,
    "warn_cold": 1,
    "warn_snow": 1,
    "warn_sunny": 0,
    "warn_hot": 1,
    "show_allday_events": 1,
    "timed_events_enabled": 1,
    "allday_rain": 1,
    "allday_wind": 1,
    "allday_cold": 1,
    "allday_snow": 1,
    "allday_sunny": 0,
    "allday_hot": 1,
    "warm_threshold": 14.0,
    "hot_threshold": 28.0,
}


def create_user_preferences_table(db_path: str) -> None:
    conn = _conn(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id         INTEGER PRIMARY KEY,
                cold_threshold  REAL    DEFAULT 3.0,
                warn_in_allday  INTEGER DEFAULT 1,
                warn_rain       INTEGER DEFAULT 1,
                warn_wind       INTEGER DEFAULT 1,
                warn_cold       INTEGER DEFAULT 1,
                warn_snow       INTEGER DEFAULT 1,
                warn_sunny      INTEGER DEFAULT 0,
                updated_at      TEXT
            )
        """)
        # Migrate: add new columns for existing DBs
        new_columns = [
            "show_allday_events  INTEGER DEFAULT 1",
            "timed_events_enabled INTEGER DEFAULT 1",
            "allday_rain         INTEGER DEFAULT 1",
            "allday_wind         INTEGER DEFAULT 1",
            "allday_cold         INTEGER DEFAULT 1",
            "allday_snow         INTEGER DEFAULT 1",
            "allday_sunny        INTEGER DEFAULT 0",
            "warn_hot            INTEGER DEFAULT 1",
            "allday_hot          INTEGER DEFAULT 1",
            "warm_threshold      REAL    DEFAULT 14.0",
            "hot_threshold       REAL    DEFAULT 28.0",
        ]
        for col_def in new_columns:
            try:
                conn.execute(f"ALTER TABLE user_preferences ADD COLUMN {col_def}")
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()
    finally:
        conn.close()


def get_user_preferences(db_path: str, user_id: int):
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()


def upsert_user_preferences(
    db_path: str,
    user_id: int,
    cold_threshold: float,
    warn_in_allday: int,
    warn_rain: int,
    warn_wind: int,
    warn_cold: int,
    warn_snow: int,
    warn_sunny: int,
    show_allday_events: int = 1,
    timed_events_enabled: int = 1,
    allday_rain: int = 1,
    allday_wind: int = 1,
    allday_cold: int = 1,
    allday_snow: int = 1,
    allday_sunny: int = 0,
    warm_threshold: float = 14.0,
    hot_threshold: float = 28.0,
    allday_hot: int = 1,
    warn_hot: int = 1,
) -> None:
    updated_at = datetime.now().isoformat()
    conn = _conn(db_path)
    try:
        conn.execute(
            """
            INSERT INTO user_preferences
                (user_id, cold_threshold, warn_in_allday, warn_rain, warn_wind, warn_cold, warn_snow, warn_sunny,
                 show_allday_events, timed_events_enabled, allday_rain, allday_wind, allday_cold, allday_snow, allday_sunny,
                 warm_threshold, hot_threshold, allday_hot, warn_hot,
                 updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                cold_threshold       = excluded.cold_threshold,
                warn_in_allday       = excluded.warn_in_allday,
                warn_rain            = excluded.warn_rain,
                warn_wind            = excluded.warn_wind,
                warn_cold            = excluded.warn_cold,
                warn_snow            = excluded.warn_snow,
                warn_sunny           = excluded.warn_sunny,
                show_allday_events   = excluded.show_allday_events,
                timed_events_enabled = excluded.timed_events_enabled,
                allday_rain          = excluded.allday_rain,
                allday_wind          = excluded.allday_wind,
                allday_cold          = excluded.allday_cold,
                allday_snow          = excluded.allday_snow,
                allday_sunny         = excluded.allday_sunny,
                warm_threshold       = excluded.warm_threshold,
                hot_threshold        = excluded.hot_threshold,
                allday_hot           = excluded.allday_hot,
                warn_hot             = excluded.warn_hot,
                updated_at           = excluded.updated_at
            """,
            (user_id, cold_threshold, warn_in_allday, warn_rain, warn_wind, warn_cold, warn_snow, warn_sunny,
             show_allday_events, timed_events_enabled, allday_rain, allday_wind, allday_cold, allday_snow, allday_sunny,
             warm_threshold, hot_threshold, allday_hot, warn_hot,
             updated_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_last_forecast_update(db_path: str, locations: list) -> str | None:
    """Return the most recent last_updated timestamp across the given locations."""
    if not locations:
        return None
    conn = _conn(db_path)
    try:
        placeholders = ",".join("?" * len(locations))
        cur = conn.cursor()
        cur.execute(
            f"SELECT MAX(last_updated) FROM forecast WHERE location IN ({placeholders})",
            locations,
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def update_user_email(db_path: str, user_id: int, new_email: str) -> None:
    """Update a user's email. Raises sqlite3.IntegrityError if email already taken."""
    conn = _conn(db_path)
    try:
        conn.execute("UPDATE users SET email = ? WHERE id = ?", (new_email, user_id))
        conn.commit()
    finally:
        conn.close()


def update_user_password(db_path: str, user_id: int, new_password: str) -> None:
    """Hash and store a new password for the given user."""
    password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    conn = _conn(db_path)
    try:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        conn.commit()
    finally:
        conn.close()


def delete_user_account(db_path: str, user_id: int) -> None:
    """Soft-delete a user account and remove their feed token (stops feed immediately)."""
    conn = _conn(db_path)
    try:
        conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        conn.execute("DELETE FROM feed_tokens WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def wipe_accounts(db_path: str) -> None:
    """Delete all user accounts, locations, and feed tokens. Forecast cache is preserved.
    Only call this when WIPE_ACCOUNTS_ON_START is set — debug/dev use only.
    TODO: remove this call from app startup once onboarding is stable.
    """
    conn = _conn(db_path)
    try:
        conn.execute("DELETE FROM feed_tokens")
        conn.execute("DELETE FROM user_locations")
        conn.execute("DELETE FROM users")
        conn.commit()
        logger.warning("WIPE_ACCOUNTS_ON_START is set — all user accounts have been deleted.")
    finally:
        conn.close()
