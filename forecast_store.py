# forecast_store.py

import sqlite3
import os
import logging

from datetime import datetime
from weather_cal.utils.logging_config import setup_logging
from dotenv import load_dotenv

setup_logging()
logger = logging.getLogger(__name__)

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "forecast.db")

class ForecastStore:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()
        logger.info(f"Initialized ForecastStore with database at {self.db_path}")

    def _init_db(self):
        """Initialize the SQLite database and create the forecast table if not exists."""
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
        conn.commit()
        conn.close()

    def get_forecast_record(self, date, location):
        """Retrieve a forecast for a given date and location."""
        logger.info(f"Fetching forecast for date={date}, location={location}")
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT morning_temp, morning_emoji, afternoon_temp, afternoon_emoji, high, low, summary, description FROM forecast WHERE date=? AND location=?",
                    (date, location))
        row = cur.fetchone()
        conn.close()
        return row

    def upsert_forecast(self, date, location, morning_temp, morning_emoji, afternoon_temp, afternoon_emoji, high, low, summary, description):
        """Insert or update a forecast entry."""
        logger.info(f"Upserting forecast for date={date}, location={location}")
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO forecast (date, location, morning_temp, morning_emoji, afternoon_temp, afternoon_emoji, high, low, summary, description, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, location) DO UPDATE SET
                morning_temp=excluded.morning_temp,
                morning_emoji=excluded.morning_emoji,
                afternoon_temp=excluded.afternoon_temp,
                afternoon_emoji=excluded.afternoon_emoji,
                high=excluded.high,
                low=excluded.low,
                summary=excluded.summary,
                description=excluded.description,
                last_updated=excluded.last_updated
        """, (date, location, morning_temp, morning_emoji, afternoon_temp, afternoon_emoji, high, low, summary, description, datetime.now().isoformat()))
        conn.commit()
        conn.close()