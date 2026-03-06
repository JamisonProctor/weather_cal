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
        location="Munich, Germany",
        high=20,
        low=10,
        summary="Sunny",
        description="Clear skies",
        fetch_time="2098-12-31T23:00:00",
    )
    past_forecast = Forecast(
        date="2000-01-01",
        location="Munich, Germany",
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
    assert stored.location == "Munich, Germany"
    assert stored.high == 20
    assert stored.low == 10
    assert stored.summary == "Sunny"
    assert stored.description == "Clear skies"
    assert stored.fetch_time == "2098-12-31T23:00:00"


def test_get_forecasts_for_locations(store):
    munich = Forecast(
        date="2099-01-01",
        location="Munich, Germany",
        high=15,
        low=5,
        summary="Sunny",
        description="Clear skies",
    )
    berlin = Forecast(
        date="2099-01-01",
        location="Berlin, Germany",
        high=12,
        low=3,
        summary="Cloudy",
        description="Overcast",
    )
    store.upsert_forecast(munich)
    store.upsert_forecast(berlin)

    forecasts = store.get_forecasts_for_locations(["Munich, Germany", "Berlin, Germany"])
    locations = {f.location for f in forecasts}
    assert "Munich, Germany" in locations
    assert "Berlin, Germany" in locations
    assert len(forecasts) == 2


def test_get_forecasts_for_locations_empty_list(store):
    assert store.get_forecasts_for_locations([]) == []


def test_upsert_and_retrieve_preserves_hourly_data(store):
    forecast = Forecast(
        date="2099-06-01",
        location="Munich, Germany",
        high=25,
        low=15,
        summary="Sunny",
        description="Clear",
        times=["2099-06-01T06:00", "2099-06-01T12:00"],
        temps=[15.5, 25.3],
        codes=[0, 1],
        rain=[0, 10],
        winds=[5, 8],
        timezone="Europe/Berlin",
    )
    store.upsert_forecast(forecast)
    results = store.get_forecasts_for_locations(["Munich, Germany"])
    assert len(results) == 1
    r = results[0]
    assert r.times == ["2099-06-01T06:00", "2099-06-01T12:00"]
    assert r.temps == [15.5, 25.3]
    assert r.codes == [0, 1]
    assert r.rain == [0, 10]
    assert r.winds == [5, 8]
    assert r.timezone == "Europe/Berlin"


def test_get_forecasts_future_deserializes_hourly_json(store):
    forecast = Forecast(
        date="2099-07-01",
        location="Berlin, Germany",
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
    berlin = [f for f in results if f.location == "Berlin, Germany"]
    assert len(berlin) >= 1
    assert berlin[0].times == ["2099-07-01T10:00"]
    assert berlin[0].temps == [30]


def test_upsert_forecast_updates_existing_row(store):
    original = Forecast(
        date="2099-02-01",
        location="Munich, Germany",
        high=10,
        low=1,
        summary="Cloudy",
        description="First pass",
        fetch_time="2099-01-31T22:00:00",
    )
    updated = Forecast(
        date="2099-02-01",
        location="Munich, Germany",
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
