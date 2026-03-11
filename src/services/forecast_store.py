# forecast_store.py

import json
import sqlite3
import os
import logging

from datetime import datetime
from src.utils.logging_config import setup_logging
from dotenv import load_dotenv

setup_logging()
logger = logging.getLogger(__name__)

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "data/forecast.db")

class ForecastStore:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()
        logger.info(f"Initialized ForecastStore with database at {self.db_path}")

    def _init_db(self):
        """Initialize the SQLite database and create tables if not exists."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS forecast (
                date TEXT,
                location TEXT,
                morning_temp REAL,
                morning_emoji TEXT,
                afternoon_temp REAL,
                afternoon_emoji TEXT,
                high REAL,
                low REAL,
                summary TEXT,
                description TEXT,
                last_updated TEXT,
                PRIMARY KEY (date, location)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                created_at    TEXT    NOT NULL,
                is_active     INTEGER NOT NULL DEFAULT 1
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_locations (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                location     TEXT    NOT NULL,
                lat          REAL,
                lon          REAL,
                timezone     TEXT,
                created_at   TEXT    NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS feed_tokens (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token      TEXT    NOT NULL UNIQUE,
                created_at TEXT    NOT NULL
            )
        """)
        # Add columns introduced after initial schema (idempotent)
        for col_def in ["hourly_json TEXT", "timezone TEXT"]:
            try:
                cur.execute(f"ALTER TABLE forecast ADD COLUMN {col_def}")
            except sqlite3.OperationalError:
                pass  # column already exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS poll_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                token      TEXT NOT NULL,
                polled_at  TEXT NOT NULL,
                user_agent TEXT
            )
        """)
        # GDPR data minimization: clear any existing IP data from legacy column
        try:
            cur.execute("UPDATE poll_log SET ip_address = NULL WHERE ip_address IS NOT NULL")
        except sqlite3.OperationalError:
            pass  # column doesn't exist on fresh databases
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_poll_log_token_polled
            ON poll_log (token, polled_at)
        """)
        # Add analytics columns to feed_tokens (idempotent)
        for col_def in [
            "last_polled_at TEXT",
            "poll_count INTEGER DEFAULT 0",
            "last_user_agent TEXT",
            "settings_clicks INTEGER DEFAULT 0",
        ]:
            try:
                cur.execute(f"ALTER TABLE feed_tokens ADD COLUMN {col_def}")
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()
        conn.close()

    def upsert_forecast(self, forecast):
        """Insert or update a forecast entry using a Forecast object."""
        logger.info(f"Upserting forecast for date={forecast.date}, location={forecast.location}")
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        hourly_json = json.dumps({
            "times": forecast.times or [],
            "temps": forecast.temps or [],
            "codes": forecast.codes or [],
            "rain": forecast.rain or [],
            "precipitation": forecast.precipitation or [],
            "winds": forecast.winds or [],
        })
        cur.execute("""
            INSERT INTO forecast (date, location, high, low, summary, description, last_updated, hourly_json, timezone)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, location) DO UPDATE SET
                high=excluded.high,
                low=excluded.low,
                summary=excluded.summary,
                description=excluded.description,
                last_updated=excluded.last_updated,
                hourly_json=excluded.hourly_json,
                timezone=excluded.timezone
        """, (forecast.date, forecast.location, forecast.high, forecast.low,
              forecast.summary, forecast.description, forecast.fetch_time or datetime.now().isoformat(),
              hourly_json, forecast.timezone))
        conn.commit()
        conn.close()

    def get_forecasts_for_locations(self, locations: list, days: int = 14) -> list:
        """Retrieve forecasts from today onwards for a list of locations."""
        if not locations:
            return []
        from datetime import date
        today = date.today().isoformat()
        placeholders = ",".join("?" * len(locations))
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(f"""
            SELECT date, location, high, low, summary, description, last_updated, hourly_json, timezone
            FROM forecast
            WHERE date >= ? AND location IN ({placeholders})
            ORDER BY location, date ASC
            LIMIT ?
        """, [today] + list(locations) + [days * len(locations)])
        rows = cur.fetchall()
        conn.close()
        from src.models.forecast import Forecast
        forecasts = []
        for row in rows:
            hourly = json.loads(row[7]) if row[7] else {}
            forecasts.append(Forecast(
                date=row[0],
                location=row[1],
                high=row[2],
                low=row[3],
                summary=row[4],
                description=row[5],
                fetch_time=row[6],
                times=hourly.get("times", []),
                temps=hourly.get("temps", []),
                codes=hourly.get("codes", []),
                rain=hourly.get("rain", []),
                precipitation=hourly.get("precipitation", []),
                winds=hourly.get("winds", []),
                timezone=row[8],
            ))
        return forecasts

    def get_forecasts_future(self, days:int = 7):
        """Retrieve forecasts from today onwards, limited to the given number of days."""
        from datetime import date, timedelta
        today = date.today().isoformat()
        logger.info(f"Fetching forecasts from DB starting {today} limited to {days} days")
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            SELECT date, location, high, low, summary, description, last_updated, hourly_json, timezone
            FROM forecast
            WHERE date >= ?
            ORDER BY date ASC
            LIMIT ?
        """, (today, days))
        rows = cur.fetchall()
        conn.close()
        forecasts = []
        from src.models.forecast import Forecast
        for row in rows:
            hourly = json.loads(row[7]) if row[7] else {}
            forecasts.append(Forecast(
                date=row[0],
                location=row[1],
                high=row[2],
                low=row[3],
                summary=row[4],
                description=row[5],
                fetch_time=row[6],
                times=hourly.get("times", []),
                temps=hourly.get("temps", []),
                codes=hourly.get("codes", []),
                rain=hourly.get("rain", []),
                precipitation=hourly.get("precipitation", []),
                winds=hourly.get("winds", []),
                timezone=row[8],
            ))
        return forecasts
