import os
import sys
import logging
import time
import schedule

from src.services.forecast_service import ForecastService
from src.services.forecast_formatting import format_summary, format_detailed_forecast, get_warning_windows
from src.utils.logging_config import setup_logging
from src.utils.location_management import get_locations
from src.services.forecast_store import ForecastStore

setup_logging()
logger = logging.getLogger(__name__)

from src.integrations.calendar_service import CalendarService


def get_schedule_time() -> str:
    schedule_time = os.getenv("SCHEDULE_TIME", "00:23")
    try:
        time.strptime(schedule_time, "%H:%M")
    except ValueError:
        logger.warning("Invalid SCHEDULE_TIME=%s. Falling back to 00:23.", schedule_time)
        return "00:23"
    return schedule_time

def main():
    locations = get_locations()
    store = ForecastStore()

    forecast_days = 14

    try:
        calendar = CalendarService()

        # Fetch new forecasts, store them, and sync warning events while hourly data is available
        for loc in locations:
            forecasts = ForecastService.fetch_forecasts(location=loc, forecast_days=forecast_days)

            for forecast in forecasts:
                forecast.summary = format_summary(forecast)
                forecast.description = format_detailed_forecast(forecast)
                store.upsert_forecast(forecast)

                warning_windows = get_warning_windows(forecast)
                tz = forecast.timezone or "UTC"
                logger.info(
                    "Syncing %d warning event(s) for date=%s, location=%s",
                    len(warning_windows),
                    forecast.date,
                    forecast.location,
                )
                calendar.sync_warning_events(forecast.date, forecast.location, warning_windows, tz)

        # Populate calendar with all-day summary events from DB
        logger.info("Retrieving forecasts from DB for calendar population...")
        all_forecasts = store.get_forecasts_future(days=forecast_days)

        for forecast in all_forecasts:
            logger.info(f"Updating calendar for date={forecast.date}, location={forecast.location}")
            calendar.upsert_event(forecast)

    except Exception as e:
        logger.error(f"Failed to fetch, process, store, or update calendar with forecasts: {e}", exc_info=True)

def schedule_jobs():
    job = schedule.every().day.at(get_schedule_time()).do(main)
    logger.info(f"Scheduled job: {job.job_func.__name__} → next run at {job.next_run}")

    logger.info("Scheduler started. Waiting for tasks...")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    schedule_jobs()
