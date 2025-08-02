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

# Tests for get_forecast removed because get_forecast method no longer exists.
# Only keeping initialization test as upsert functionality is already covered by other integration tests.
