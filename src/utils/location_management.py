import os
import logging

logger = logging.getLogger(__name__)

def load_locations_from_db():
    """Stub: Future DB integration. Returns empty list for now."""
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