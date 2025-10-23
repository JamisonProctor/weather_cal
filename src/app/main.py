import os
import sys
import logging
import time
import schedule

from src.services.forecast_service import ForecastService
from src.services.forecast_formatting import format_summary, format_detailed_forecast
from src.utils.logging_config import setup_logging
from src.utils.location_management import get_locations
from src.services.forecast_store import ForecastStore

setup_logging()
logger = logging.getLogger(__name__)

from src.integrations.calendar_service import CalendarService

def main():
    locations = get_locations()
    store = ForecastStore()

    forecast_days = 7

    try:
        # Fetch new forecasts and store them
        for loc in locations:
            forecasts = ForecastService.fetch_forecasts(location=loc, forecast_days=forecast_days)

            for forecast in forecasts:
                forecast.summary = format_summary(forecast)
                forecast.description = format_detailed_forecast(forecast)
                store.upsert_forecast(forecast)

        # Populate calendar with future events from DB
        logger.info("Retrieving forecasts from DB for calendar population...")
        all_forecasts = store.get_forecasts_future(days=forecast_days)

        calendar = CalendarService()

        for forecast in all_forecasts:
            logger.info(f"Updating calendar for date={forecast.date}, location={forecast.location}")
            calendar.upsert_event(forecast)

    except Exception as e:
        logger.error(f"Failed to fetch, process, store, or update calendar with forecasts: {e}", exc_info=True)

def schedule_jobs():
    # For testing, run every minute
    # schedule.every(1).minutes.do(main)

    # For production, switch to midnight only
    schedule.every().day.at("00:00").do(main)

    logger.info("Scheduler started. Waiting for tasks...")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    schedule_jobs()
