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
