"""Test suite for the core weather forecast app, covering DB operations and API parsing."""

import os
import sqlite3
import pytest
from weather_cal.sqlite_store import init_db, upsert_forecast, get_forecast_record

TEST_DB = "test_forecast.db"

@pytest.fixture(scope="function")
def setup_db():
    # Remove old test DB if exists
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_forecast_update_detection(setup_db):
    date = "2025-08-01"
    location = "Munich, Germany"

    # --- First run: store initial forecast ---
    upsert_forecast(date, location, 15, "☀️", 22, "🌧️", 28, 15, TEST_DB)
    record1 = get_forecast_record(date, location, TEST_DB)
    assert record1[0] == 15  # morning temp
    assert record1[1] == "☀️"

    # --- Second run: changed morning temp and emoji ---
    upsert_forecast(date, location, 18, "🌤️", 22, "🌧️", 28, 15, TEST_DB)
    record2 = get_forecast_record(date, location, TEST_DB)
    
    # Verify updated values
    assert record2[0] == 18
    assert record2[1] == "🌤️"

def test_no_update_when_forecast_unchanged(setup_db):
    date = "2025-08-02"
    location = "Munich, Germany"

    # First run: store forecast
    upsert_forecast(date, location, 16, "☀️", 23, "🌤️", 29, 16, TEST_DB)
    record1 = get_forecast_record(date, location, TEST_DB)
    assert record1[0] == 16
    assert record1[1] == "☀️"

    # Second run: identical forecast
    upsert_forecast(date, location, 16, "☀️", 23, "🌤️", 29, 16, TEST_DB)
    record2 = get_forecast_record(date, location, TEST_DB)

    # Record should remain unchanged
    assert record2 == record1

def test_multiple_forecasts_records(setup_db):
    """Test storing and retrieving multiple forecast records for different dates."""
    data = [
        ("2025-08-03", "Munich, Germany", 14, "☀️", 20, "🌤️", 25, 14),
        ("2025-08-04", "Munich, Germany", 15, "🌤️", 21, "☁️", 26, 15),
        ("2025-08-05", "Munich, Germany", 16, "☀️", 22, "🌧️", 27, 16)
    ]
    # Insert all records
    for entry in data:
        upsert_forecast(*entry, TEST_DB)
    
    # Retrieve and check each record
    for entry in data:
        record = get_forecast_record(entry[0], entry[1], TEST_DB)
        assert record is not None
        assert int(record[0]) == entry[2]
        assert record[1] == entry[3]
        assert int(record[2]) == entry[4]
        assert record[3] == entry[5]


# --- New test for fetch_forecast API parsing ---
def test_fetch_forecast_parsing(monkeypatch):
    """Test that fetch_forecast returns correct structure from mocked API response."""
    from weather_cal.weather_service import fetch_forecast

    # Mock API responses
    def mock_get(url, params=None, timeout=10):
        class MockResponse:
            def raise_for_status(self): pass
            def json(self):
                return {
                    "hourly": {
                        "time": ["2025-08-06T06:00", "2025-08-06T12:00"],
                        "temperature_2m": [15, 22],
                        "weathercode": [1, 61]
                    }
                }
        return MockResponse()

    monkeypatch.setattr("weather_cal.weather_service.requests.get", mock_get)
    
    forecasts = fetch_forecast("Munich")
    assert isinstance(forecasts, list)
    assert len(forecasts) == 1
    day = forecasts[0]
    assert "date" in day
    assert "summary" in day
    assert "high" in day
    assert "low" in day
    assert "➡️" in day["summary"]

def test_fetch_forecast_error_handling(monkeypatch):
    """Test that fetch_forecast handles API errors gracefully without crashing."""
    from weather_cal.weather_service import fetch_forecast

    # Mock requests.get to raise an exception
    def mock_get(*args, **kwargs):
        raise Exception("API failure")

    monkeypatch.setattr("weather_cal.weather_service.requests.get", mock_get)

    try:
        fetch_forecast("Munich")
    except Exception as e:
        assert str(e) == "API failure"
    else:
        pytest.fail("Expected an exception due to API failure but none occurred")