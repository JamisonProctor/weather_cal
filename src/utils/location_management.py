import os
import sqlite3
import logging

logger = logging.getLogger(__name__)


def load_locations_from_db(db_path: str = None) -> list:
    """Load distinct active locations from the user_locations table.

    Returns a list of dicts with keys: location, lat, lon, timezone.
    """
    if db_path is None:
        db_path = os.getenv("DB_PATH", "data/forecast.db")
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT ul.location, ul.lat, ul.lon, ul.timezone
            FROM user_locations ul
            JOIN users u ON ul.user_id = u.id
            WHERE u.is_active = 1
        """)
        rows = cur.fetchall()
        conn.close()
        return [
            {"location": row[0], "lat": row[1], "lon": row[2], "timezone": row[3]}
            for row in rows
        ]
    except Exception as e:
        logger.warning(f"Could not load locations from DB: {e}")
        return []


def get_locations():
    """Get locations from DB if available, otherwise use default env location.

    Returns a list of dicts with keys: location, lat, lon, timezone.
    """
    locations = load_locations_from_db()
    if not locations:
        default_location = os.getenv("DEFAULT_LOCATION")
        if not default_location:
            logger.error("No locations found in DB and DEFAULT_LOCATION is not set in environment variables.")
            raise EnvironmentError("No locations available to process forecasts.")
        logger.warning("No locations found in DB. Falling back to DEFAULT_LOCATION from environment.")
        locations = [{"location": default_location, "lat": None, "lon": None, "timezone": None}]
    return locations
