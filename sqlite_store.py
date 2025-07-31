
import sqlite3
from datetime import datetime

import os
from dotenv import load_dotenv
load_dotenv()
DB_PATH = os.getenv("DB_PATH", "forecast.db")

def init_db(db_path=DB_PATH):
    """Initialize the SQLite database and create the forecast table if not exists."""
    conn = sqlite3.connect(db_path)
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
            last_updated TEXT,
            PRIMARY KEY (date, location)
        )
    """)
    conn.commit()
    conn.close()

def get_forecast_record(date, location, db_path=DB_PATH):
    """Retrieve a forecast for a given date and location."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT morning_temp, morning_emoji, afternoon_temp, afternoon_emoji, high, low FROM forecast WHERE date=? AND location=?",
                (date, location))
    row = cur.fetchone()
    conn.close()
    return row

def upsert_forecast(date, location, morning_temp, morning_emoji, afternoon_temp, afternoon_emoji, high, low, db_path=DB_PATH):
    """Insert or update a forecast entry."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO forecast (date, location, morning_temp, morning_emoji, afternoon_temp, afternoon_emoji, high, low, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, location) DO UPDATE SET
            morning_temp=excluded.morning_temp,
            morning_emoji=excluded.morning_emoji,
            afternoon_temp=excluded.afternoon_temp,
            afternoon_emoji=excluded.afternoon_emoji,
            high=excluded.high,
            low=excluded.low,
            last_updated=excluded.last_updated
    """, (date, location, morning_temp, morning_emoji, afternoon_temp, afternoon_emoji, high, low, datetime.now().isoformat()))
    conn.commit()
    conn.close()