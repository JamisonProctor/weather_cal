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