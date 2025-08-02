import os
import sys
import logging

from src.services.forecast_service import ForecastService
from src.services.forecast_formatting import format_summary, format_detailed_forecast
from src.utils.logging_config import setup_logging
from src.utils.location_management import get_locations
from src.services.forecast_store import ForecastStore

setup_logging()
logger = logging.getLogger(__name__)

def main():
    locations = get_locations()
    store = ForecastStore()

    try:
        for loc in locations:
            forecasts = ForecastService.fetch_forecasts(location=loc)

            for forecast in forecasts:
                forecast.summary = format_summary(forecast)
                forecast.description = format_detailed_forecast(forecast)
                store.upsert_forecast(forecast)

    except Exception as e:
        logger.error(f"Failed to fetch, process, or store forecasts: {e}", exc_info=True)

if __name__ == "__main__":
    main()