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
from src.integrations.calendar_service import CalendarService
from src.integrations.google_push import (
    create_google_tokens_table,
    get_google_connected_users,
    push_events_for_user,
)
from src.web.db import get_user_preferences, get_user_locations, DEFAULT_PREFS, resolve_prefs

setup_logging()
logger = logging.getLogger(__name__)


def _push_google_calendars(db_path: str = None):
    """Push forecast events to Google Calendar for all connected users."""
    db_path = db_path or os.getenv("DB_PATH", "data/forecast.db")
    try:
        create_google_tokens_table(db_path)
    except Exception:
        logger.exception("Failed to ensure google_tokens table")
        return

    connected = get_google_connected_users(db_path)
    if not connected:
        return

    store = ForecastStore(db_path=db_path)
    for user_info in connected:
        user_id = user_info["user_id"]
        try:
            locations = get_user_locations(db_path, user_id)
            prefs_row = get_user_preferences(db_path, user_id)
            prefs = resolve_prefs(prefs_row)
            for loc in locations:
                forecasts = store.get_forecasts_for_locations([loc["location"]], days=14)
                push_events_for_user(db_path, user_id, forecasts, prefs, loc["location"], loc["timezone"])
            logger.info("Google push complete for user_id=%s", user_id)
        except Exception:
            logger.exception("Google push failed for user_id=%s", user_id)


def get_schedule_time() -> str:
    schedule_time = os.getenv("SCHEDULE_TIME", "00:23")
    try:
        time.strptime(schedule_time, "%H:%M")
    except ValueError:
        logger.warning("Invalid SCHEDULE_TIME=%s. Falling back to 00:23.", schedule_time)
        return "00:23"
    return schedule_time

def short_term_main():
    """Refresh near-term (3-day) forecasts for all active user locations every 4 hours."""
    locations = get_locations()
    store = ForecastStore()
    for loc in locations:
        try:
            forecasts = ForecastService.fetch_forecasts(
                location=loc["location"], forecast_days=3,
                lat=loc["lat"], lon=loc["lon"], timezone=loc["timezone"],
            )
            for f in forecasts:
                f.summary = format_summary(f)
                f.description = format_detailed_forecast(f)
                store.upsert_forecast(f)
        except Exception:
            logger.exception("Short-term fetch failed for location=%s", loc["location"])

    _push_google_calendars()


def main():
    locations = get_locations()
    store = ForecastStore()

    forecast_days = 14

    calendar = None
    if os.getenv("ENABLE_GOOGLE_CALENDAR_SYNC"):
        try:
            calendar = CalendarService()
        except Exception as e:
            logger.error(f"Failed to initialize CalendarService: {e}", exc_info=True)

    try:
        for loc in locations:
            forecasts = ForecastService.fetch_forecasts(
                location=loc["location"], forecast_days=forecast_days,
                lat=loc["lat"], lon=loc["lon"], timezone=loc["timezone"],
            )

            for forecast in forecasts:
                forecast.summary = format_summary(forecast)
                forecast.description = format_detailed_forecast(forecast)
                store.upsert_forecast(forecast)

                if calendar:
                    warning_windows = get_warning_windows(forecast)
                    tz = forecast.timezone or "UTC"
                    logger.info(
                        "Syncing %d warning event(s) for date=%s, location=%s",
                        len(warning_windows),
                        forecast.date,
                        forecast.location,
                    )
                    calendar.sync_warning_events(forecast.date, forecast.location, warning_windows, tz)

        if calendar:
            logger.info("Retrieving forecasts from DB for calendar population...")
            all_forecasts = store.get_forecasts_future(days=forecast_days)
            for forecast in all_forecasts:
                logger.info(f"Updating calendar for date={forecast.date}, location={forecast.location}")
                calendar.upsert_event(forecast)

    except Exception as e:
        logger.error(f"Failed to fetch, process, store, or update calendar with forecasts: {e}", exc_info=True)

    _push_google_calendars()

def schedule_jobs():
    job = schedule.every().day.at(get_schedule_time()).do(main)
    logger.info(f"Scheduled job: {job.job_func.__name__} → next run at {job.next_run}")

    intraday_job = schedule.every(4).hours.do(short_term_main)
    logger.info(f"Scheduled job: {intraday_job.job_func.__name__} → next run at {intraday_job.next_run}")

    short_term_main()

    logger.info("Scheduler started. Waiting for tasks...")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    schedule_jobs()
