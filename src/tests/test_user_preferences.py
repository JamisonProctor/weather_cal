import pytest

from src.models.forecast import Forecast
from src.integrations.ics_service import generate_ics
from src.services.forecast_formatting import format_summary, get_warning_windows
from src.web.db import (
    DEFAULT_PREFS,
    get_user_preferences,
    upsert_user_preferences,
)


def _make_forecast(times, temps, codes, rain, winds, date="2025-08-01", precipitation=None):
    return Forecast(
        date=date,
        location="Munich",
        high=max(temps),
        low=min(temps),
        times=times,
        temps=temps,
        codes=codes,
        rain=rain,
        precipitation=precipitation or [0]*len(times),
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
    assert DEFAULT_PREFS["warm_threshold"] == 14.0
    assert DEFAULT_PREFS["hot_threshold"] == 28.0
    assert DEFAULT_PREFS["warn_in_allday"] == 1
    assert DEFAULT_PREFS["warn_rain"] == 1
    assert DEFAULT_PREFS["warn_wind"] == 1
    assert DEFAULT_PREFS["warn_cold"] == 1
    assert DEFAULT_PREFS["warn_snow"] == 1
    assert DEFAULT_PREFS["warn_sunny"] == 1
    assert DEFAULT_PREFS["warn_hot"] == 1
    assert DEFAULT_PREFS["show_allday_events"] == 1
    assert DEFAULT_PREFS["timed_events_enabled"] == 1
    assert DEFAULT_PREFS["allday_rain"] == 1
    assert DEFAULT_PREFS["allday_wind"] == 1
    assert DEFAULT_PREFS["allday_cold"] == 1
    assert DEFAULT_PREFS["allday_snow"] == 1
    assert DEFAULT_PREFS["allday_sunny"] == 0
    assert DEFAULT_PREFS["allday_hot"] == 1


# --- format_summary prefs tests ---

def test_format_summary_hides_warnings_when_warn_in_allday_false():
    forecast = _make_forecast(
        times=["2025-01-01T10:00", "2025-01-01T11:00"],
        temps=[1, 1],
        codes=[61, 61],
        rain=[60, 60],
        winds=[35, 35],
        precipitation=[1.5, 2.0],
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
        precipitation=[2.0, 3.0],
    )
    prefs = {**DEFAULT_PREFS, "allday_rain": 0}
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
        precipitation=[2.0, 3.0],
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


# --- New prefs: show_allday_events / timed_events_enabled / allday_* ---

def _parse_ics_events(ics_bytes):
    from icalendar import Calendar
    cal = Calendar.from_ical(ics_bytes)
    return [c for c in cal.walk() if c.name == "VEVENT"]


def _make_rainy_forecast():
    return _make_forecast(
        times=["2025-08-01T10:00", "2025-08-01T11:00", "2025-08-01T12:00"],
        temps=[15, 15, 15],
        codes=[61, 61, 61],
        rain=[70, 70, 70],
        winds=[5, 5, 5],
        precipitation=[2.0, 3.0, 2.5],
    )


def test_upsert_includes_new_columns(db_path):
    upsert_user_preferences(
        db_path, 1,
        cold_threshold=3.0, warn_in_allday=1, warn_rain=1,
        warn_wind=1, warn_cold=1, warn_snow=1, warn_sunny=0,
        show_allday_events=0, timed_events_enabled=0,
        allday_rain=0, allday_wind=1, allday_cold=1, allday_snow=1, allday_sunny=1,
    )
    prefs = get_user_preferences(db_path, 1)
    assert prefs["show_allday_events"] == 0
    assert prefs["timed_events_enabled"] == 0
    assert prefs["allday_rain"] == 0
    assert prefs["allday_sunny"] == 1


def test_show_allday_events_false_suppresses_allday_event():
    forecast = _make_rainy_forecast()
    prefs = {**DEFAULT_PREFS, "show_allday_events": 0}
    events = _parse_ics_events(generate_ics([forecast], "Munich", prefs=prefs))
    allday = [e for e in events if not hasattr(e["DTSTART"].dt, "hour")]
    assert len(allday) == 0


def test_timed_events_enabled_false_suppresses_timed_events():
    forecast = _make_rainy_forecast()
    prefs = {**DEFAULT_PREFS, "timed_events_enabled": 0}
    events = _parse_ics_events(generate_ics([forecast], "Munich", prefs=prefs))
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    assert len(timed) == 0


def test_get_warning_windows_hot_enabled():
    forecast = _make_forecast(
        times=["2025-08-01T10:00", "2025-08-01T11:00"],
        temps=[32, 33],
        codes=[1, 1],
        rain=[0, 0],
        winds=[5, 5],
    )
    prefs = {**DEFAULT_PREFS, "warn_hot": 1}
    windows = get_warning_windows(forecast, prefs=prefs)
    hot = [w for w in windows if w.warning_type == "hot"]
    assert len(hot) == 1
    assert hot[0].emoji == "🥵"


def test_get_warning_windows_hot_disabled_by_default():
    forecast = _make_forecast(
        times=["2025-08-01T10:00", "2025-08-01T11:00"],
        temps=[32, 33],
        codes=[1, 1],
        rain=[0, 0],
        winds=[5, 5],
    )
    windows = get_warning_windows(forecast, prefs=None)
    assert not any(w.warning_type == "hot" for w in windows)


def test_sunny_requires_warm_temp():
    forecast = _make_forecast(
        times=["2025-08-01T10:00", "2025-08-01T11:00"],
        temps=[5, 6],
        codes=[0, 0],
        rain=[0, 0],
        winds=[5, 5],
    )
    prefs = {**DEFAULT_PREFS, "warn_sunny": 1}
    windows = get_warning_windows(forecast, prefs=prefs)
    assert not any(w.warning_type == "sunny" for w in windows)


def test_allday_rain_false_hides_rain_icon_but_timed_event_remains():
    forecast = _make_rainy_forecast()
    # allday_rain=0 hides icon in all-day summary; warn_rain=1 keeps timed event
    prefs = {**DEFAULT_PREFS, "allday_rain": 0, "warn_rain": 1}
    events = _parse_ics_events(generate_ics([forecast], "Munich", prefs=prefs))
    allday = next(e for e in events if not hasattr(e["DTSTART"].dt, "hour"))
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    assert "☂️" not in str(allday["SUMMARY"])
    assert any("☂️" in str(e["SUMMARY"]) and "mm" in str(e["SUMMARY"]) for e in timed)
