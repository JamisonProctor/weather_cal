import os
import sqlite3
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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


def group_locations_by_tz_offset(locations: list = None) -> dict[int, list[dict]]:
    """Group locations by their current UTC offset (rounded to nearest hour).

    Returns a dict mapping offset_hours -> list of location dicts.
    E.g. {1: [munich, paris], 9: [tokyo]}
    """
    if locations is None:
        locations = get_locations()

    groups: dict[int, list[dict]] = {}
    now = datetime.now(timezone.utc)

    for loc in locations:
        tz_name = loc.get("timezone")
        if not tz_name:
            offset_hours = 0
        else:
            try:
                tz = ZoneInfo(tz_name)
                offset_seconds = now.astimezone(tz).utcoffset().total_seconds()
                offset_hours = round(offset_seconds / 3600)
            except (KeyError, AttributeError):
                logger.warning("Unknown timezone %s for %s, defaulting to UTC", tz_name, loc.get("location"))
                offset_hours = 0

        groups.setdefault(offset_hours, []).append(loc)

    return groups


def local_to_utc(local_time: str, utc_offset_hours: int) -> str:
    """Convert a local time string like '05:30' to UTC given an offset.

    Returns a time string like '04:30'. Wraps around midnight.
    """
    parts = local_time.split(":")
    hour = int(parts[0]) - utc_offset_hours
    minute = int(parts[1])
    hour = hour % 24
    return f"{hour:02d}:{minute:02d}"
