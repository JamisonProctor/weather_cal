import os
import sqlite3
import logging

logger = logging.getLogger(__name__)


def load_locations_from_db(db_path: str = None) -> list:
    """Load distinct active locations from the user_locations table."""
    if db_path is None:
        db_path = os.getenv("DB_PATH", "data/forecast.db")
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT ul.location FROM user_locations ul
            JOIN users u ON ul.user_id = u.id
            WHERE u.is_active = 1
        """)
        rows = cur.fetchall()
        conn.close()
        return [row[0] for row in rows]
    except Exception as e:
        logger.warning(f"Could not load locations from DB: {e}")
        return []


def get_locations():
    """Get locations from DB if available, otherwise use default env location."""
    locations = load_locations_from_db()
    if not locations:
        default_location = os.getenv("DEFAULT_LOCATION")
        if not default_location:
            logger.error("No locations found in DB and DEFAULT_LOCATION is not set in environment variables.")
            raise EnvironmentError("No locations available to process forecasts.")
        logger.warning("No locations found in DB. Falling back to DEFAULT_LOCATION from environment.")
        locations = [default_location]
    return locations
