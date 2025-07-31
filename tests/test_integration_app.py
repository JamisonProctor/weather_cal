

"""Integration test for the weather_cal application.
This test simulates the full flow: fetch forecast -> store in DB -> create/update calendar event.
All external services (weather API, Google Calendar API) are mocked.
"""

import pytest

def test_full_integration_weather_to_calendar(monkeypatch, tmp_path):
    from weather_cal import weather_service, sqlite_store, calendar_service

    # Mock weather data
    mock_forecasts = [
        {
            "date": "2025-08-01",
            "summary": "☀️15° ➡️ 🌧️22°",
            "high": 22,
            "low": 15
        }
    ]

    calls = []

    # Mock fetch_forecast to return mock data
    monkeypatch.setattr(weather_service, "fetch_forecast", lambda loc: mock_forecasts)

    # Use temporary test database
    test_db_path = tmp_path / "forecast_test.db"
    monkeypatch.setattr(sqlite_store, "DB_PATH", str(test_db_path))

    # Mock upsert_event to capture calls
    def mock_upsert_event(date, summary, location):
        calls.append({"date": date, "summary": summary, "location": location})
        return {"id": "event123"}
    monkeypatch.setattr(calendar_service, "upsert_event", mock_upsert_event)
    monkeypatch.setattr(calendar_service, "get_calendar_service", lambda: None)

    # Run flow: store forecast and trigger calendar update
    sqlite_store.init_db(str(test_db_path))
    forecasts = weather_service.fetch_forecast("Munich, Germany")
    for day in forecasts:
        parts = day['summary'].split("➡️")
        morning_emoji = parts[0][0]
        morning_temp = ''.join(filter(str.isdigit, parts[0]))
        afternoon_emoji = parts[1][-1]
        afternoon_temp = ''.join(filter(str.isdigit, parts[1]))

        sqlite_store.upsert_forecast(
            day['date'], "Munich, Germany",
            float(morning_temp), morning_emoji,
            float(afternoon_temp), afternoon_emoji,
            day['high'], day['low'],
            str(test_db_path)
        )
        calendar_service.upsert_event(day['date'], day['summary'], "Munich, Germany")

    # Assertions
    assert len(calls) == 1
    assert calls[0]["date"] == "2025-08-01"
    assert "☀️15°" in calls[0]["summary"]
    assert calls[0]["location"] == "Munich, Germany"