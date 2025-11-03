# forecast_store.py

import sqlite3
import os
import logging

from datetime import datetime
from src.utils.logging_config import setup_logging
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

    def upsert_forecast(self, forecast):
        """Insert or update a forecast entry using a Forecast object."""
        logger.info(f"Upserting forecast for date={forecast.date}, location={forecast.location}")
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO forecast (date, location, high, low, summary, description, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, location) DO UPDATE SET
                high=excluded.high,
                low=excluded.low,
                summary=excluded.summary,
                description=excluded.description,
                last_updated=excluded.last_updated
        """, (forecast.date, forecast.location, forecast.high, forecast.low,
              forecast.summary, forecast.description, forecast.fetch_time or datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_forecasts_future(self, days:int = 7):
        """Retrieve forecasts from today onwards, limited to the given number of days."""
        from datetime import date, timedelta
        today = date.today().isoformat()
        logger.info(f"Fetching forecasts from DB starting {today} limited to {days} days")
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            SELECT date, location, high, low, summary, description, last_updated
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
            forecasts.append(Forecast(
                date=row[0],
                location=row[1],
                high=row[2],
                low=row[3],
                summary=row[4],
                description=row[5],
                fetch_time=row[6],
                times=[],
                temps=[],
                codes=[],
                rain=[],
                winds=[]
            ))
        return forecasts
