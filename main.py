import os
from weather_service import fetch_forecasts_for_locations
from sqlite_store import init_db, upsert_forecast, get_forecast_record, DB_PATH
from calendar_service import upsert_event

# Load configuration from .env
DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "local_user")
DEFAULT_LOCATION = os.getenv("DEFAULT_LOCATION", "Munich, Germany")
DEFAULT_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

# Example list of users (can be extended later)
USERS = [
    {"user_id": DEFAULT_USER_EMAIL, "location": DEFAULT_LOCATION, "calendar_id": DEFAULT_CALENDAR_ID},
]

def main():
    logger.info("Fetching 7-day weather forecast for all user locations...")
    init_db(DB_PATH)

    # Collect all unique locations
    locations = [u["location"] for u in USERS]
    forecasts_by_location = fetch_forecasts_for_locations(locations)

    for user in USERS:
        user_id = user["user_id"]
        location = user["location"]
        calendar_id = user["calendar_id"]
        forecasts = forecasts_by_location.get(location, [])

        for day in forecasts:
            parts = day['summary'].split("➡️")
            morning_emoji = parts[0][0]
            morning_temp = ''.join(filter(str.isdigit, parts[0]))
            afternoon_emoji = parts[1][-1]
            afternoon_temp = ''.join(filter(str.isdigit, parts[1]))

            upsert_forecast(
                day['date'], location,
                float(morning_temp), morning_emoji,
                float(afternoon_temp), afternoon_emoji,
                day['high'], day['low'],
                DB_PATH
            )

            # Create or update Google Calendar event
            upsert_event(day['date'], day['summary'], location)

        logger.info(f"Forecasts stored and synced for user: {user_id} ({location})")
        for day in forecasts:
            record = get_forecast_record(day['date'], location, DB_PATH)
            if record:
                logger.info(f"{day['date']} | {record[1]}{int(record[0])}° ➡️ {record[3]}{int(record[2])}° "
                            f"(High: {record[4]}° Low: {record[5]}°)")


if __name__ == "__main__":
    import sys
    import schedule
    import time
    import logging

    # Setup logging
    os.makedirs("data", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler('data/weather_cal.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger(__name__)

    # Schedule the main job to run every day at midnight
    schedule.every().day.at("00:00").do(main)

    logger.info("Weather Calendar service started. Waiting to run daily at midnight...")

    while True:
        schedule.run_pending()
        time.sleep(30)