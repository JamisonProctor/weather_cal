import os
import logging
import time
from datetime import date, timedelta

import schedule

from src.services.forecast_service import ForecastService
from src.services.forecast_formatting import format_summary, format_detailed_forecast
from src.utils.logging_config import setup_logging
from src.utils.location_management import get_locations, group_locations_by_tz_offset, local_to_utc
from src.services.forecast_store import ForecastStore
from src.integrations.google_push import (
    create_google_tokens_table,
    get_google_connected_users,
    push_events_for_user,
)
from src.constants import DEFAULT_PREFS
from src.web.db import get_user_preferences, get_user_locations, resolve_prefs

setup_logging()
logger = logging.getLogger(__name__)

# Tier schedule defaults (local times)
DEFAULT_TIER1_TIMES = "05:30,11:00,15:30,18:30,22:00"
DEFAULT_TIER2_TIMES = "06:00,17:00"
DEFAULT_TIER3_TIME = "02:00"


def _get_tier_times() -> tuple[list[str], list[str], list[str]]:
    """Read tier schedule times from env vars or use defaults."""
    tier1 = os.getenv("TIER1_TIMES", DEFAULT_TIER1_TIMES).split(",")
    tier2 = os.getenv("TIER2_TIMES", DEFAULT_TIER2_TIMES).split(",")
    tier3 = os.getenv("TIER3_TIME", DEFAULT_TIER3_TIME).split(",")
    return [t.strip() for t in tier1], [t.strip() for t in tier2], [t.strip() for t in tier3]


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


def _process_and_store(forecasts, store, prefs=None):
    """Format summaries/descriptions and upsert forecasts into the store."""
    for f in forecasts:
        f.summary = format_summary(f, prefs) if prefs else format_summary(f)
        f.description = format_detailed_forecast(f, prefs) if prefs else format_detailed_forecast(f)
        store.upsert_forecast(f)


def refresh_tier1(locations: list[dict]):
    """Refresh today + tomorrow forecasts (days 0-1) via batch."""
    if not locations:
        return
    store = ForecastStore()
    try:
        batch_result = ForecastService.fetch_forecasts_batch(
            locations, forecast_days=2,
        )
        for loc_name, forecasts in batch_result.items():
            _process_and_store(forecasts, store)
        logger.info("Tier 1 refresh complete for %d locations", len(locations))
    except Exception:
        logger.exception("Tier 1 refresh failed")
    _push_google_calendars()


def refresh_tier2(locations: list[dict]):
    """Refresh days 2-4 forecasts via batch with start_date/end_date."""
    if not locations:
        return
    store = ForecastStore()
    today = date.today()
    start = (today + timedelta(days=2)).isoformat()
    end = (today + timedelta(days=4)).isoformat()
    try:
        batch_result = ForecastService.fetch_forecasts_batch(
            locations, start_date=start, end_date=end,
        )
        for loc_name, forecasts in batch_result.items():
            _process_and_store(forecasts, store)
        logger.info("Tier 2 refresh complete for %d locations", len(locations))
    except Exception:
        logger.exception("Tier 2 refresh failed")
    _push_google_calendars()


def refresh_tier3(locations: list[dict]):
    """Refresh days 5-14 forecasts via batch with start_date/end_date."""
    if not locations:
        return
    store = ForecastStore()
    today = date.today()
    start = (today + timedelta(days=5)).isoformat()
    end = (today + timedelta(days=14)).isoformat()
    try:
        batch_result = ForecastService.fetch_forecasts_batch(
            locations, start_date=start, end_date=end,
        )
        for loc_name, forecasts in batch_result.items():
            _process_and_store(forecasts, store)
        logger.info("Tier 3 refresh complete for %d locations", len(locations))
    except Exception:
        logger.exception("Tier 3 refresh failed")
    _push_google_calendars()


def get_schedule_time() -> str:
    schedule_time = os.getenv("SCHEDULE_TIME", "00:23")
    try:
        time.strptime(schedule_time, "%H:%M")
    except ValueError:
        logger.warning("Invalid SCHEDULE_TIME=%s. Falling back to 00:23.", schedule_time)
        return "00:23"
    return schedule_time


def short_term_main():
    """Refresh near-term (3-day) forecasts for all active user locations. Legacy fallback."""
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
    """Full 14-day refresh for all locations. Legacy fallback."""
    locations = get_locations()
    store = ForecastStore()

    forecast_days = 14

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

    except Exception as e:
        logger.error(f"Failed to fetch, process, or store forecasts: {e}", exc_info=True)

    _push_google_calendars()


def _schedule_tier_jobs(tz_groups: dict[int, list[dict]]):
    """Schedule tier 1/2/3 jobs for each timezone group."""
    tier1_times, tier2_times, tier3_times = _get_tier_times()

    for offset, locations in tz_groups.items():
        loc_names = [loc["location"] for loc in locations]
        logger.info("Scheduling tiers for UTC%+d: %s", offset, loc_names)

        for local_time in tier1_times:
            utc_time = local_to_utc(local_time, offset)
            job = schedule.every().day.at(utc_time).do(refresh_tier1, locations=locations)
            job.tag(f"tier1_utc{offset}")

        for local_time in tier2_times:
            utc_time = local_to_utc(local_time, offset)
            job = schedule.every().day.at(utc_time).do(refresh_tier2, locations=locations)
            job.tag(f"tier2_utc{offset}")

        for local_time in tier3_times:
            utc_time = local_to_utc(local_time, offset)
            job = schedule.every().day.at(utc_time).do(refresh_tier3, locations=locations)
            job.tag(f"tier3_utc{offset}")


def reschedule():
    """Clear and recreate all tier jobs. Handles DST transitions and new users."""
    logger.info("Rescheduling all tier jobs")
    schedule.clear("tier1")
    schedule.clear("tier2")
    schedule.clear("tier3")
    # Clear all tier-tagged jobs
    for job in list(schedule.get_jobs()):
        tags = getattr(job, "tags", set())
        if any(t.startswith("tier") for t in tags):
            schedule.cancel_job(job)

    tz_groups = group_locations_by_tz_offset()
    _schedule_tier_jobs(tz_groups)
    logger.info("Rescheduled %d jobs across %d timezone groups", len(schedule.get_jobs()), len(tz_groups))


def schedule_jobs():
    """Set up the tiered scheduler and run the event loop."""
    tz_groups = group_locations_by_tz_offset()
    _schedule_tier_jobs(tz_groups)

    # Daily reschedule at 00:00 UTC to handle DST transitions and new users
    reschedule_job = schedule.every().day.at("00:00").do(reschedule)
    reschedule_job.tag("reschedule")

    # Run tier 1 immediately on startup for all groups
    for offset, locations in tz_groups.items():
        refresh_tier1(locations)

    total_jobs = len(schedule.get_jobs())
    logger.info("Scheduler started with %d jobs across %d timezone groups. Waiting for tasks...",
                total_jobs, len(tz_groups))

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    schedule_jobs()
