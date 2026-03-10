import secrets
import sqlite3
import logging
from datetime import datetime, timedelta

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


def get_feedback(db_path: str) -> list:
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            """SELECT f.email, f.description, f.locations, f.created_at,
                      COALESCE(ft.last_user_agent, '') AS last_user_agent
               FROM feedback f
               LEFT JOIN feed_tokens ft ON f.user_id = ft.user_id
               ORDER BY f.created_at DESC"""
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["calendar_app"] = _detect_calendar_app(d.pop("last_user_agent"))
            result.append(d)
        return result
    finally:
        conn.close()


DEFAULT_PREFS = {
    "cold_threshold": 3.0,
    "warn_in_allday": 1,
    "warn_rain": 1,
    "warn_wind": 1,
    "warn_cold": 1,
    "warn_snow": 1,
    "warn_sunny": 1,
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
    "temp_unit": "C",
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
                warn_sunny      INTEGER DEFAULT 1,
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
            "temp_unit           TEXT    DEFAULT 'C'",
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
    temp_unit: str = "C",
) -> None:
    updated_at = datetime.now().isoformat()
    conn = _conn(db_path)
    try:
        conn.execute(
            """
            INSERT INTO user_preferences
                (user_id, cold_threshold, warn_in_allday, warn_rain, warn_wind, warn_cold, warn_snow, warn_sunny,
                 show_allday_events, timed_events_enabled, allday_rain, allday_wind, allday_cold, allday_snow, allday_sunny,
                 warm_threshold, hot_threshold, allday_hot, warn_hot, temp_unit,
                 updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                temp_unit            = excluded.temp_unit,
                updated_at           = excluded.updated_at
            """,
            (user_id, cold_threshold, warn_in_allday, warn_rain, warn_wind, warn_cold, warn_snow, warn_sunny,
             show_allday_events, timed_events_enabled, allday_rain, allday_wind, allday_cold, allday_snow, allday_sunny,
             warm_threshold, hot_threshold, allday_hot, warn_hot, temp_unit,
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
    """Soft-delete a user account and clean up all related personal data."""
    conn = _conn(db_path)
    try:
        # Get user's feed tokens to clean up poll_log
        cur = conn.execute("SELECT token FROM feed_tokens WHERE user_id = ?", (user_id,))
        tokens = [row["token"] for row in cur.fetchall()]
        if tokens:
            placeholders = ",".join("?" * len(tokens))
            conn.execute(f"DELETE FROM poll_log WHERE token IN ({placeholders})", tokens)
        # Delete user-linked data
        conn.execute("DELETE FROM user_preferences WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_locations WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM feedback WHERE user_id = ?", (user_id,))
        try:
            conn.execute("DELETE FROM google_tokens WHERE user_id = ?", (user_id,))
        except sqlite3.OperationalError:
            pass  # table may not exist yet
        conn.execute("DELETE FROM feed_tokens WHERE user_id = ?", (user_id,))
        # Soft-delete user record (preserves email uniqueness constraint)
        conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def _detect_calendar_app(user_agent: str) -> str:
    """Identify the calendar app from a User-Agent string."""
    ua = user_agent.lower()
    if any(x in ua for x in ["cfnetwork", "dataaccessd", "calendarstore", "darwin"]):
        return "Apple Calendar"
    if any(x in ua for x in ["google-calendar", "googlebot"]):
        return "Google Calendar"
    if "fantastical" in ua:
        return "Fantastical"
    if "busycal" in ua:
        return "BusyCal"
    if any(x in ua for x in ["microsoft", "outlook"]):
        return "Outlook"
    if any(x in ua for x in ["thunderbird", "lightning"]):
        return "Thunderbird"
    if not ua.strip():
        return "Unknown"
    return "Other"


def update_feed_poll(db_path: str, token: str, user_agent: str) -> None:
    """Record an ICS feed poll: update timestamp, increment count, store UA."""
    now = datetime.now().isoformat()
    conn = _conn(db_path)
    try:
        conn.execute(
            """UPDATE feed_tokens
               SET last_polled_at = ?,
                   poll_count = COALESCE(poll_count, 0) + 1,
                   last_user_agent = ?
               WHERE token = ?""",
            (now, user_agent, token),
        )
        conn.commit()
    finally:
        conn.close()


def log_feed_poll(db_path: str, token: str, user_agent: str) -> None:
    """Insert a row into poll_log for granular tracking."""
    now = datetime.now().isoformat()
    conn = _conn(db_path)
    try:
        conn.execute(
            "INSERT INTO poll_log (token, polled_at, user_agent) VALUES (?, ?, ?)",
            (token, now, user_agent),
        )
        conn.commit()
    finally:
        conn.close()


def increment_settings_clicks(db_path: str, user_id: int) -> None:
    """Increment the settings link click counter for a user's feed token."""
    conn = _conn(db_path)
    try:
        conn.execute(
            "UPDATE feed_tokens SET settings_clicks = COALESCE(settings_clicks, 0) + 1 WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()


def export_user_data(db_path: str, user_id: int) -> dict:
    """Return all personal data for a user as a dictionary (GDPR data export)."""
    conn = _conn(db_path)
    try:
        cur = conn.cursor()

        # Account info
        cur.execute("SELECT id, email, created_at FROM users WHERE id = ?", (user_id,))
        user_row = cur.fetchone()
        account = dict(user_row) if user_row else {}

        # Locations
        cur.execute("SELECT location, lat, lon, timezone, created_at FROM user_locations WHERE user_id = ?", (user_id,))
        locations = [dict(r) for r in cur.fetchall()]

        # Preferences
        cur.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,))
        prefs_row = cur.fetchone()
        preferences = dict(prefs_row) if prefs_row else {}

        # Feed tokens (metadata only, not the token itself)
        cur.execute(
            "SELECT created_at, last_polled_at, poll_count FROM feed_tokens WHERE user_id = ?",
            (user_id,),
        )
        feed_tokens = [dict(r) for r in cur.fetchall()]

        # Poll log entries
        cur.execute("SELECT token FROM feed_tokens WHERE user_id = ?", (user_id,))
        tokens = [row["token"] for row in cur.fetchall()]
        poll_logs = []
        if tokens:
            placeholders = ",".join("?" * len(tokens))
            cur.execute(
                f"SELECT polled_at, user_agent FROM poll_log WHERE token IN ({placeholders}) ORDER BY polled_at DESC",
                tokens,
            )
            poll_logs = [dict(r) for r in cur.fetchall()]

        # Feedback
        cur.execute(
            "SELECT description, calendar_app, locations, created_at FROM feedback WHERE user_id = ?",
            (user_id,),
        )
        feedback = [dict(r) for r in cur.fetchall()]

        # Google Calendar connection
        try:
            cur.execute(
                "SELECT connected_at, status FROM google_tokens WHERE user_id = ?",
                (user_id,),
            )
            google_row = cur.fetchone()
            google_connection = dict(google_row) if google_row else None
        except sqlite3.OperationalError:
            google_connection = None

        return {
            "account": account,
            "locations": locations,
            "preferences": preferences,
            "feed_tokens": feed_tokens,
            "poll_logs": poll_logs,
            "feedback": feedback,
            "google_calendar": google_connection,
        }
    finally:
        conn.close()


def get_admin_stats(db_path: str) -> dict:
    """Return aggregated analytics for the admin dashboard."""
    conn = _conn(db_path)
    try:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
        total_users = cur.fetchone()[0]

        cur.execute(
            """SELECT COUNT(DISTINCT ul.location)
               FROM user_locations ul
               JOIN users u ON ul.user_id = u.id
               WHERE u.is_active = 1"""
        )
        unique_locations = cur.fetchone()[0]

        changed_prefs_sql = """
            cold_threshold != 3.0
            OR warm_threshold != 14.0
            OR hot_threshold != 28.0
            OR warn_in_allday != 1
            OR warn_rain != 1
            OR warn_wind != 1
            OR warn_cold != 1
            OR warn_snow != 1
            OR warn_sunny != 0
            OR warn_hot != 1
            OR show_allday_events != 1
            OR timed_events_enabled != 1
            OR allday_rain != 1
            OR allday_wind != 1
            OR allday_cold != 1
            OR allday_snow != 1
            OR allday_sunny != 0
            OR allday_hot != 1
        """
        cur.execute(
            f"""SELECT COUNT(*)
                FROM user_preferences up
                JOIN users u ON up.user_id = u.id
                WHERE u.is_active = 1 AND ({changed_prefs_sql})"""
        )
        changed_prefs_count = cur.fetchone()[0]

        cur.execute(
            """SELECT COALESCE(SUM(ft.poll_count), 0), COALESCE(SUM(ft.settings_clicks), 0)
               FROM feed_tokens ft
               JOIN users u ON ft.user_id = u.id
               WHERE u.is_active = 1"""
        )
        row = cur.fetchone()
        total_polls = row[0]
        total_settings_clicks = row[1]

        now = datetime.now()
        twenty_four_hours_ago = (now - timedelta(hours=24)).isoformat()

        # Per-token poll counts from poll_log for last 24h
        cur.execute(
            """SELECT token, COUNT(*) AS cnt FROM poll_log
               WHERE polled_at >= ? GROUP BY token""",
            (twenty_four_hours_ago,),
        )
        token_polls_24h = {row["token"]: row["cnt"] for row in cur.fetchall()}

        cur.execute(
            f"""SELECT
                    u.email,
                    ul.location,
                    u.created_at,
                    ft.last_polled_at,
                    COALESCE(ft.poll_count, 0) AS poll_count,
                    ft.token,
                    ft.created_at AS token_created_at,
                    ft.last_user_agent,
                    COALESCE(ft.settings_clicks, 0) AS settings_clicks,
                    (SELECT CASE WHEN COUNT(*) > 0 THEN 1 ELSE 0 END
                     FROM user_preferences up
                     WHERE up.user_id = u.id AND ({changed_prefs_sql})) AS changed_prefs
                FROM users u
                LEFT JOIN user_locations ul ON ul.user_id = u.id
                LEFT JOIN feed_tokens ft ON ft.user_id = u.id
                WHERE u.is_active = 1
                ORDER BY u.created_at DESC"""
        )
        rows = cur.fetchall()

        users = []
        for r in rows:
            ua = r["last_user_agent"] or ""
            last_poll = r["last_polled_at"] or ""
            token = r["token"] or ""
            token_created = r["token_created_at"]
            polls_last_24h = token_polls_24h.get(token, 0)
            if token_created:
                days_since = (now - datetime.fromisoformat(token_created)).total_seconds() / 86400
                low_polls = polls_last_24h < 1 and days_since > 1.0
            else:
                low_polls = False
            users.append({
                "email": r["email"],
                "location": r["location"] or "",
                "created_at": (r["created_at"] or "")[:10],
                "last_polled_at": last_poll[:10] if last_poll else "",
                "poll_count": r["poll_count"],
                "polls_last_24h": polls_last_24h,
                "low_polls": low_polls,
                "calendar_app": _detect_calendar_app(ua),
                "settings_clicks": r["settings_clicks"],
                "changed_prefs": bool(r["changed_prefs"]),
            })

        return {
            "total_users": total_users,
            "unique_locations": unique_locations,
            "changed_prefs_count": changed_prefs_count,
            "total_polls": total_polls,
            "total_settings_clicks": total_settings_clicks,
            "users": users,
        }
    finally:
        conn.close()


