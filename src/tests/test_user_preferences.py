import pytest

from src.models.forecast import Forecast
from src.services.forecast_formatting import format_summary, get_warning_windows
from src.services.forecast_store import ForecastStore
from src.web.db import (
    DEFAULT_PREFS,
    create_user_preferences_table,
    get_user_preferences,
    upsert_user_preferences,
)


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    ForecastStore(db_path=path)
    create_user_preferences_table(path)
    return path


def _make_forecast(times, temps, codes, rain, winds, date="2025-08-01"):
    return Forecast(
        date=date,
        location="Munich",
        high=max(temps),
        low=min(temps),
        times=times,
        temps=temps,
        codes=codes,
        rain=rain,
        winds=winds,
    )


# --- DB tests ---

def test_get_user_preferences_returns_none_when_missing(db_path):
    assert get_user_preferences(db_path, 999) is None


def test_upsert_then_get_user_preferences(db_path):
    upsert_user_preferences(
        db_path, 1,
        cold_threshold=5.0, warn_in_allday=1, warn_rain=0,
        warn_wind=1, warn_cold=1, warn_snow=0, warn_sunny=1,
    )
    prefs = get_user_preferences(db_path, 1)
    assert prefs is not None
    assert prefs["cold_threshold"] == 5.0
    assert prefs["warn_rain"] == 0
    assert prefs["warn_sunny"] == 1
    assert prefs["warn_snow"] == 0


def test_upsert_user_preferences_updates_existing(db_path):
    upsert_user_preferences(
        db_path, 1,
        cold_threshold=3.0, warn_in_allday=1, warn_rain=1,
        warn_wind=1, warn_cold=1, warn_snow=1, warn_sunny=0,
    )
    upsert_user_preferences(
        db_path, 1,
        cold_threshold=10.0, warn_in_allday=0, warn_rain=0,
        warn_wind=0, warn_cold=0, warn_snow=0, warn_sunny=1,
    )
    prefs = get_user_preferences(db_path, 1)
    assert prefs["cold_threshold"] == 10.0
    assert prefs["warn_in_allday"] == 0
    assert prefs["warn_rain"] == 0
    assert prefs["warn_sunny"] == 1


def test_default_prefs_values():
    assert DEFAULT_PREFS["cold_threshold"] == 3.0
    assert DEFAULT_PREFS["warn_in_allday"] == 1
    assert DEFAULT_PREFS["warn_rain"] == 1
    assert DEFAULT_PREFS["warn_wind"] == 1
    assert DEFAULT_PREFS["warn_cold"] == 1
    assert DEFAULT_PREFS["warn_snow"] == 1
    assert DEFAULT_PREFS["warn_sunny"] == 0


# --- format_summary prefs tests ---

def test_format_summary_hides_warnings_when_warn_in_allday_false():
    forecast = _make_forecast(
        times=["2025-01-01T10:00", "2025-01-01T11:00"],
        temps=[1, 1],
        codes=[61, 61],
        rain=[60, 60],
        winds=[35, 35],
    )
    prefs = {**DEFAULT_PREFS, "warn_in_allday": 0}
    summary = format_summary(forecast, prefs=prefs)
    assert "⚠️" not in summary


def test_format_summary_filters_rain_warning():
    forecast = _make_forecast(
        times=["2025-01-01T10:00", "2025-01-01T11:00"],
        temps=[15, 15],
        codes=[61, 61],
        rain=[70, 70],
        winds=[5, 5],
    )
    prefs = {**DEFAULT_PREFS, "warn_rain": 0}
    summary = format_summary(forecast, prefs=prefs)
    assert "☂️" not in summary


def test_format_summary_uses_custom_cold_threshold():
    forecast = _make_forecast(
        times=["2025-06-01T10:00", "2025-06-01T11:00"],
        temps=[15, 15],
        codes=[1, 1],
        rain=[0, 0],
        winds=[5, 5],
    )
    # At default threshold (3°C), 15°C is not cold
    assert "🥶" not in format_summary(forecast)
    # At threshold=20°C, 15°C IS cold
    prefs = {**DEFAULT_PREFS, "cold_threshold": 20.0}
    summary = format_summary(forecast, prefs=prefs)
    assert "🥶" in summary


# --- get_warning_windows prefs tests ---

def test_get_warning_windows_filters_rain_when_disabled():
    forecast = _make_forecast(
        times=["2025-08-01T10:00", "2025-08-01T11:00"],
        temps=[15, 15],
        codes=[61, 61],
        rain=[70, 70],
        winds=[5, 5],
    )
    prefs = {**DEFAULT_PREFS, "warn_rain": 0}
    windows = get_warning_windows(forecast, prefs=prefs)
    assert not any(w.warning_type == "rain" for w in windows)


def test_get_warning_windows_sunny_enabled():
    forecast = _make_forecast(
        times=["2025-08-01T10:00", "2025-08-01T11:00", "2025-08-01T12:00"],
        temps=[25, 26, 27],
        codes=[0, 0, 1],
        rain=[0, 0, 0],
        winds=[5, 5, 5],
    )
    prefs = {**DEFAULT_PREFS, "warn_sunny": 1}
    windows = get_warning_windows(forecast, prefs=prefs)
    sunny = [w for w in windows if w.warning_type == "sunny"]
    assert len(sunny) == 1
    assert sunny[0].emoji == "☀️"


def test_get_warning_windows_sunny_disabled_by_default():
    forecast = _make_forecast(
        times=["2025-08-01T10:00", "2025-08-01T11:00"],
        temps=[25, 25],
        codes=[0, 0],
        rain=[0, 0],
        winds=[5, 5],
    )
    windows = get_warning_windows(forecast, prefs=None)
    assert not any(w.warning_type == "sunny" for w in windows)


def test_get_warning_windows_custom_cold_threshold():
    forecast = _make_forecast(
        times=["2025-08-01T10:00", "2025-08-01T11:00"],
        temps=[15, 15],
        codes=[1, 1],
        rain=[0, 0],
        winds=[5, 5],
    )
    # Default: no cold warning at 15°C
    assert not any(w.warning_type == "cold" for w in get_warning_windows(forecast))
    # With cold_threshold=20°C, 15°C IS cold
    prefs = {**DEFAULT_PREFS, "cold_threshold": 20.0}
    windows = get_warning_windows(forecast, prefs=prefs)
    cold = [w for w in windows if w.warning_type == "cold"]
    assert len(cold) == 1
