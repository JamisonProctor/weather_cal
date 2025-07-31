from weather_service import fetch_forecast, DEFAULT_LOCATION
from sqlite_store import init_db, upsert_forecast, get_forecast_record, DB_PATH

def main():
    print("Fetching 7-day weather forecast...\n")
    init_db(DB_PATH)
    forecasts = fetch_forecast(DEFAULT_LOCATION)

    # Store forecasts in DB
    for day in forecasts:
        # Parse forecast summary to extract emojis and temps
        parts = day['summary'].split("➡️")
        morning_emoji = parts[0][0]
        morning_temp = ''.join(filter(str.isdigit, parts[0]))
        afternoon_emoji = parts[1][-1]
        afternoon_temp = ''.join(filter(str.isdigit, parts[1]))

        upsert_forecast(
            day['date'], DEFAULT_LOCATION,
            float(morning_temp), morning_emoji,
            float(afternoon_temp), afternoon_emoji,
            day['high'], day['low'],
            DB_PATH
        )

    print("\nForecasts stored in database:\n")
    for day in forecasts:
        record = get_forecast_record(day['date'], DEFAULT_LOCATION, DB_PATH)
        if record:
            print(f"{day['date']} | {record[1]}{int(record[0])}° ➡️ {record[3]}{int(record[2])}° "
                  f"(High: {record[4]}° Low: {record[5]}°)")

if __name__ == "__main__":
    main()