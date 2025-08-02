import os
import sys
import logging

from services.forecast_service import ForecastService
from services.forecast_formatting import format_summary, format_detailed_forecast
from utils.logging_config import setup_logging
from utils.location_management import get_locations
from services.forecast_store import ForecastStore

setup_logging()
logger = logging.getLogger(__name__)

def main():
    locations = get_locations()
    store = ForecastStore()

    try:
        forecasts = ForecastService.fetch_forecasts(location=locations)

        for forecast in forecasts:
            forecast.summary = format_summary(forecast)
            forecast.description = format_detailed_forecast(forecast)
            store.upsert_forecast(forecast)

        # Temporary verification of stored forecasts
        try:
            stored = store.get_all_forecasts()
            logger.info(f"Total forecasts stored: {len(stored)}")
            for f in stored:
                logger.info(f"Stored forecast: {f.date} - {f.summary}")
        except Exception as verify_error:
            logger.error(f"Error verifying stored forecasts: {verify_error}", exc_info=True)

    except Exception as e:
        logger.error(f"Failed to fetch, process, or store forecasts: {e}", exc_info=True)

if __name__ == "__main__":
    main()