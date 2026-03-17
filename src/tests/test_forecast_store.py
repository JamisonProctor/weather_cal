import os
import pytest

from src.services.forecast_store import ForecastStore
from src.models.forecast import Forecast


@pytest.fixture
def temp_db_path(tmp_path):
    return tmp_path / "test_forecast.db"


@pytest.fixture
def store(temp_db_path):
    fs = ForecastStore(db_path=str(temp_db_path))
    yield fs


def test_initialization_creates_db(store, temp_db_path):
    assert os.path.exists(temp_db_path)


def test_upsert_and_get_future_forecasts(store):
    future_forecast = Forecast(
        date="2099-01-01",
        location="Munich",
        high=20,
        low=10,
        summary="Sunny",
        description="Clear skies",
        fetch_time="2098-12-31T23:00:00",
    )
    past_forecast = Forecast(
        date="2000-01-01",
        location="Munich",
        high=5,
        low=-1,
        summary="Old",
        description="Old data",
        fetch_time="1999-12-31T23:00:00",
    )

    store.upsert_forecast(future_forecast)
    store.upsert_forecast(past_forecast)

    forecasts = store.get_forecasts_future(days=10)

    assert len(forecasts) == 1
    stored = forecasts[0]
    assert stored.date == "2099-01-01"
    assert stored.location == "Munich"
    assert stored.high == 20
    assert stored.low == 10
    assert stored.summary == "Sunny"
    assert stored.description == "Clear skies"
    assert stored.fetch_time == "2098-12-31T23:00:00"


def test_get_forecasts_for_locations(store):
    munich = Forecast(
        date="2099-01-01",
        location="Munich",
        high=15,
        low=5,
        summary="Sunny",
        description="Clear skies",
    )
    berlin = Forecast(
        date="2099-01-01",
        location="Berlin",
        high=12,
        low=3,
        summary="Cloudy",
        description="Overcast",
    )
    store.upsert_forecast(munich)
    store.upsert_forecast(berlin)

    forecasts = store.get_forecasts_for_locations(["Munich", "Berlin"])
    locations = {f.location for f in forecasts}
    assert "Munich" in locations
    assert "Berlin" in locations
    assert len(forecasts) == 2


def test_get_forecasts_for_locations_empty_list(store):
    assert store.get_forecasts_for_locations([]) == []


def test_upsert_and_retrieve_preserves_hourly_data(store):
    forecast = Forecast(
        date="2099-06-01",
        location="Munich",
        high=25,
        low=15,
        summary="Sunny",
        description="Clear",
        times=["2099-06-01T06:00", "2099-06-01T12:00"],
        temps=[15.5, 25.3],
        codes=[0, 1],
        rain=[0, 10],
        precipitation=[0, 0.5],
        winds=[5, 8],
        timezone="Europe/Berlin",
    )
    store.upsert_forecast(forecast)
    results = store.get_forecasts_for_locations(["Munich"])
    assert len(results) == 1
    r = results[0]
    assert r.times == ["2099-06-01T06:00", "2099-06-01T12:00"]
    assert r.temps == [15.5, 25.3]
    assert r.codes == [0, 1]
    assert r.rain == [0, 10]
    assert r.precipitation == [0, 0.5]
    assert r.winds == [5, 8]
    assert r.timezone == "Europe/Berlin"


def test_get_forecasts_future_deserializes_hourly_json(store):
    forecast = Forecast(
        date="2099-07-01",
        location="Berlin",
        high=30,
        low=20,
        summary="Hot",
        description="Very hot",
        times=["2099-07-01T10:00"],
        temps=[30],
        codes=[0],
        rain=[0],
        winds=[3],
        timezone="Europe/Berlin",
    )
    store.upsert_forecast(forecast)
    results = store.get_forecasts_future(days=100)
    berlin = [f for f in results if f.location == "Berlin"]
    assert len(berlin) >= 1
    assert berlin[0].times == ["2099-07-01T10:00"]
    assert berlin[0].temps == [30]


def test_upsert_forecast_updates_existing_row(store):
    original = Forecast(
        date="2099-02-01",
        location="Munich",
        high=10,
        low=1,
        summary="Cloudy",
        description="First pass",
        fetch_time="2099-01-31T22:00:00",
    )
    updated = Forecast(
        date="2099-02-01",
        location="Munich",
        high=15,
        low=3,
        summary="Warmer",
        description="Second pass",
        fetch_time="2099-01-31T23:00:00",
    )

    store.upsert_forecast(original)
    store.upsert_forecast(updated)

    forecasts = store.get_forecasts_future(days=10)

    assert len(forecasts) == 1
    stored = forecasts[0]
    assert stored.high == 15
    assert stored.low == 3
    assert stored.summary == "Warmer"
    assert stored.description == "Second pass"
    assert stored.fetch_time == "2099-01-31T23:00:00"


def test_init_db_migrates_old_location_format(tmp_path):
    """Locations stored as 'City, Country' are migrated to 'City' on init."""
    import sqlite3

    db_path = str(tmp_path / "migrate.db")

    # Create initial DB with old-format locations
    store = ForecastStore(db_path=db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Insert old-format user_locations
    cur.execute("INSERT INTO user_locations (user_id, location, lat, lon, timezone, created_at) VALUES (1, 'Munich, Germany', 48.137, 11.576, 'Europe/Berlin', '2026-01-01')")
    cur.execute("INSERT INTO user_locations (user_id, location, lat, lon, timezone, created_at) VALUES (2, 'Berlin, Germany', 52.52, 13.405, 'Europe/Berlin', '2026-01-01')")

    # Insert old-format forecast rows
    cur.execute("INSERT OR REPLACE INTO forecast (date, location, high, low, summary, description, last_updated) VALUES ('2099-01-01', 'Munich, Germany', 20, 10, 'Sunny', 'Clear', '2026-01-01T00:00:00')")
    cur.execute("INSERT OR REPLACE INTO forecast (date, location, high, low, summary, description, last_updated) VALUES ('2099-01-01', 'Berlin, Germany', 18, 8, 'Cloudy', 'Overcast', '2026-01-01T00:00:00')")
    conn.commit()
    conn.close()

    # Re-init triggers migration
    ForecastStore(db_path=db_path)

    conn = sqlite3.connect(db_path)
    locations = conn.execute("SELECT location FROM user_locations ORDER BY user_id").fetchall()
    assert locations == [("Munich",), ("Berlin",)]

    forecasts = conn.execute("SELECT location FROM forecast ORDER BY location").fetchall()
    assert forecasts == [("Berlin",), ("Munich",)]

    # No old-format rows remain
    old_rows = conn.execute("SELECT COUNT(*) FROM forecast WHERE location LIKE '%,%'").fetchone()[0]
    assert old_rows == 0
    conn.close()
