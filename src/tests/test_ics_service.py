from datetime import timedelta

from icalendar import Calendar

from src.integrations.ics_service import generate_google_active_ics, generate_ics
from src.models.forecast import Forecast


def _parse_events(ics_bytes: bytes) -> list:
    cal = Calendar.from_ical(ics_bytes)
    return [c for c in cal.walk() if c.name == "VEVENT"]


def _make_forecast(date="2026-03-10", location="Munich", timezone="Europe/Berlin", **kwargs):
    defaults = dict(
        date=date,
        location=location,
        high=15,
        low=5,
        summary="AM☀️10° / PM⛅15°",
        description="Nice day",
        times=[],
        temps=[],
        codes=[],
        rain=[],
        precipitation=[],
        winds=[],
        timezone=timezone,
    )
    defaults.update(kwargs)
    return Forecast(**defaults)


def test_no_warnings_emits_only_all_day_event():
    # Clear skies, low rain, no warnings
    forecast = _make_forecast(
        times=["2026-03-10T06:00", "2026-03-10T12:00", "2026-03-10T18:00"],
        temps=[10, 15, 12],
        codes=[0, 1, 2],
        rain=[0, 5, 10],
        winds=[5, 8, 6],
    )
    ics_bytes = generate_ics([forecast], "Munich")
    events = _parse_events(ics_bytes)

    assert len(events) == 1
    assert str(events[0]["SUMMARY"]) == forecast.summary
    # All-day event has a date (not datetime) as DTSTART
    assert not hasattr(events[0]["DTSTART"].dt, "hour")


def test_warning_produces_timed_event():
    # Precipitation >= 0.5mm for a block of hours → Rain Warning
    forecast = _make_forecast(
        times=[
            "2026-03-10T10:00",
            "2026-03-10T11:00",
            "2026-03-10T12:00",
            "2026-03-10T13:00",
        ],
        temps=[12, 12, 13, 13],
        codes=[1, 1, 1, 1],
        rain=[50, 60, 55, 45],
        precipitation=[1.2, 2.0, 1.5, 0.8],
        winds=[5, 5, 5, 5],
    )
    ics_bytes = generate_ics([forecast], "Munich")
    events = _parse_events(ics_bytes)

    # One all-day + one timed warning
    assert len(events) == 2

    timed = next(e for e in events if hasattr(e["DTSTART"].dt, "hour"))
    summary = str(timed["SUMMARY"])
    assert "☂️" in summary
    assert "mm" in summary  # shows total precipitation in mm

    # dtstart should be timezone-aware
    assert timed["DTSTART"].dt.tzinfo is not None
    assert timed["DTSTART"].dt.hour == 10
    assert timed["DTEND"].dt.hour == 14  # last hour (13:00) + 1h


def test_warning_uid_is_stable():
    forecast = _make_forecast(
        times=["2026-03-10T08:00", "2026-03-10T09:00"],
        temps=[12, 12],
        codes=[1, 1],
        rain=[50, 55],
        precipitation=[1.0, 1.5],
        winds=[5, 5],
    )

    ics1 = generate_ics([forecast], "Munich")
    ics2 = generate_ics([forecast], "Munich")

    events1 = _parse_events(ics1)
    events2 = _parse_events(ics2)

    uids1 = {str(e["UID"]) for e in events1}
    uids2 = {str(e["UID"]) for e in events2}

    assert uids1 == uids2


def test_generate_ics_with_rain_disabled_prefs():
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00"],
        temps=[12, 12],
        codes=[61, 61],
        rain=[70, 70],
        precipitation=[2.0, 3.0],
        winds=[5, 5],
    )
    prefs = {
        "warn_in_allday": 1, "warn_rain": 0, "warn_wind": 1,
        "warn_cold": 1, "warn_snow": 1, "warn_sunny": 0, "cold_threshold": 3.0,
        "show_allday_events": 1, "timed_events_enabled": 1,
        "allday_rain": 1, "allday_wind": 1, "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0,
    }
    ics_bytes = generate_ics([forecast], "Munich", prefs=prefs)
    events = _parse_events(ics_bytes)
    # Only the all-day event — no timed rain warning
    assert len(events) == 1
    assert not hasattr(events[0]["DTSTART"].dt, "hour")


def test_generate_ics_with_sunny_enabled_prefs():
    forecast = _make_forecast(
        times=["2026-03-10T06:00", "2026-03-10T09:00", "2026-03-10T12:00"],
        temps=[20, 22, 24],
        codes=[0, 0, 1],
        rain=[0, 0, 0],
        winds=[5, 5, 5],
    )
    prefs = {
        "warn_in_allday": 1, "warn_rain": 1, "warn_wind": 1,
        "warn_cold": 1, "warn_snow": 1, "warn_sunny": 1, "cold_threshold": 3.0,
        "show_allday_events": 1, "timed_events_enabled": 1,
        "allday_rain": 1, "allday_wind": 1, "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0,
    }
    ics_bytes = generate_ics([forecast], "Munich", prefs=prefs)
    events = _parse_events(ics_bytes)
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    sunny = [e for e in timed if "☀️" in str(e["SUMMARY"])]
    assert len(sunny) == 1
    summary = str(sunny[0]["SUMMARY"])
    assert "°C" in summary
    assert " ~ " in summary


def test_x_published_ttl_present():
    forecast = _make_forecast()
    ics_bytes = generate_ics([forecast], "Munich")
    assert b"X-PUBLISHED-TTL:PT12H" in ics_bytes


def test_allday_event_description_contains_settings_url():
    forecast = _make_forecast(description="Nice day")
    settings_url = "https://weathercal.app/settings"
    ics_bytes = generate_ics([forecast], "Munich", settings_url=settings_url)
    events = _parse_events(ics_bytes)
    all_day = next(e for e in events if not hasattr(e["DTSTART"].dt, "hour"))
    description = str(all_day.get("DESCRIPTION", ""))
    assert settings_url in description


def test_timed_event_description_contains_settings_url():
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00"],
        temps=[12, 12],
        codes=[61, 61],
        rain=[70, 70],
        precipitation=[2.0, 3.0],
        winds=[5, 5],
    )
    settings_url = "https://weathercal.app/settings"
    ics_bytes = generate_ics([forecast], "Munich", settings_url=settings_url)
    events = _parse_events(ics_bytes)
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    assert timed, "Expected at least one timed warning event"
    description = str(timed[0].get("DESCRIPTION", ""))
    assert settings_url in description


def test_allday_event_description_contains_feedback_email():
    forecast = _make_forecast(description="Nice day")
    ics_bytes = generate_ics([forecast], "Munich", settings_url="https://weathercal.app/settings")
    events = _parse_events(ics_bytes)
    all_day = next(e for e in events if not hasattr(e["DTSTART"].dt, "hour"))
    description = str(all_day.get("DESCRIPTION", ""))
    assert "hello@weathercal.app" in description


def test_timed_event_description_contains_feedback_email():
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00"],
        temps=[12, 12],
        codes=[61, 61],
        rain=[70, 70],
        precipitation=[2.0, 3.0],
        winds=[5, 5],
    )
    ics_bytes = generate_ics([forecast], "Munich", settings_url="https://weathercal.app/settings")
    events = _parse_events(ics_bytes)
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    assert timed, "Expected at least one timed warning event"
    description = str(timed[0].get("DESCRIPTION", ""))
    assert "hello@weathercal.app" in description


def test_vtimezone_present_when_timed_events_exist():
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00"],
        temps=[12, 12],
        codes=[1, 1],
        rain=[50, 60],
        precipitation=[1.0, 1.5],
        winds=[5, 5],
    )
    ics_bytes = generate_ics([forecast], "Munich")
    cal = Calendar.from_ical(ics_bytes)
    vtimezones = [c for c in cal.walk() if c.name == "VTIMEZONE"]
    assert len(vtimezones) >= 1
    tzids = {str(vtz["TZID"]) for vtz in vtimezones}
    assert "Europe/Berlin" in tzids


def test_generate_ics_skips_invalid_date():
    forecast = _make_forecast(date="not-a-date")
    ics_bytes = generate_ics([forecast], "Munich")
    events = _parse_events(ics_bytes)
    assert len(events) == 0


def test_generate_ics_both_allday_and_timed_disabled():
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00"],
        temps=[12, 12],
        codes=[61, 61],
        rain=[70, 70],
        precipitation=[2.0, 3.0],
        winds=[5, 5],
    )
    prefs = {
        "show_allday_events": 0, "timed_events_enabled": 0,
        "warn_in_allday": 1, "warn_rain": 1, "warn_wind": 1,
        "warn_cold": 1, "warn_snow": 1, "warn_sunny": 0, "cold_threshold": 3.0,
        "allday_rain": 1, "allday_wind": 1, "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0,
    }
    ics_bytes = generate_ics([forecast], "Munich", prefs=prefs)
    events = _parse_events(ics_bytes)
    assert len(events) == 0


def test_generate_ics_unknown_timezone_falls_back_to_utc():
    forecast = _make_forecast(
        timezone="Fake/NoSuchZone",
        times=["2026-03-10T10:00", "2026-03-10T11:00"],
        temps=[12, 12],
        codes=[61, 61],
        rain=[70, 70],
        precipitation=[2.0, 3.0],
        winds=[5, 5],
    )
    ics_bytes = generate_ics([forecast], "Munich")
    events = _parse_events(ics_bytes)
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    assert len(timed) >= 1
    # The fallback is timezone.utc, but icalendar may represent it as ZoneInfo('UTC')
    # Either way, the offset should be zero
    assert timed[0]["DTSTART"].dt.utcoffset().total_seconds() == 0


def test_merged_window_summary_sunny_fahrenheit():
    from src.services.calendar_events import _merged_window_summary
    from src.services.forecast_formatting import MergedWarningWindow
    merged = MergedWarningWindow(
        warning_types=["sunny"], emojis=["☀️"],
        start_time="2026-03-10T10:00", end_time="2026-03-10T13:00",
    )
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00", "2026-03-10T12:00"],
        temps=[20, 22, 24],
        codes=[0, 0, 1],
        rain=[0, 0, 0],
        winds=[5, 5, 5],
    )
    result = _merged_window_summary(merged, forecast, prefs={"temp_unit": "F"})
    assert "°F" in result
    assert "☀️" in result


def test_merged_window_summary_rain_shows_mm():
    from src.services.calendar_events import _merged_window_summary
    from src.services.forecast_formatting import MergedWarningWindow
    merged = MergedWarningWindow(
        warning_types=["rain"], emojis=["☂️"],
        start_time="2026-03-10T10:00", end_time="2026-03-10T13:00",
    )
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00", "2026-03-10T12:00"],
        temps=[12, 13, 14],
        codes=[61, 61, 63],
        rain=[50, 70, 60],
        precipitation=[1.2, 2.0, 1.5],
        winds=[5, 5, 5],
    )
    result = _merged_window_summary(merged, forecast)
    assert "☂️" in result
    assert "4.7mm" in result


def test_merged_window_summary_wind_shows_speed():
    from src.services.calendar_events import _merged_window_summary
    from src.services.forecast_formatting import MergedWarningWindow
    merged = MergedWarningWindow(
        warning_types=["wind"], emojis=["🌬️"],
        start_time="2026-03-10T10:00", end_time="2026-03-10T12:00",
    )
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00"],
        temps=[15, 16],
        codes=[1, 1],
        rain=[0, 0],
        winds=[35, 45],
    )
    result = _merged_window_summary(merged, forecast)
    assert "🌬️" in result
    assert "45 km/h" in result


def test_merged_window_summary_combined_shows_temp():
    from src.services.calendar_events import _merged_window_summary
    from src.services.forecast_formatting import MergedWarningWindow
    merged = MergedWarningWindow(
        warning_types=["rain", "cold"], emojis=["☂️", "🥶"],
        start_time="2026-03-10T10:00", end_time="2026-03-10T13:00",
    )
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00", "2026-03-10T12:00"],
        temps=[1, 2, 0],
        codes=[61, 61, 63],
        rain=[50, 70, 60],
        winds=[5, 5, 5],
    )
    result = _merged_window_summary(merged, forecast)
    assert "☂️" in result
    assert "🥶" in result
    assert " ~ " in result
    assert "°C" in result


def test_stable_uid_determinism():
    from src.services.calendar_events import stable_uid
    uid1 = stable_uid("2026-03-10", "Munich")
    uid2 = stable_uid("2026-03-10", "Munich")
    uid3 = stable_uid("2026-03-11", "Munich")
    assert uid1 == uid2
    assert uid1 != uid3
    assert uid1.endswith("@weathercal.app")


def test_timed_event_description_contains_hourly_weather():
    forecast = _make_forecast(
        times=[
            "2026-03-10T10:00",
            "2026-03-10T11:00",
            "2026-03-10T12:00",
            "2026-03-10T13:00",
        ],
        temps=[12, 13, 14, 13],
        codes=[61, 61, 63, 61],
        rain=[50, 60, 70, 55],
        precipitation=[1.2, 2.0, 3.5, 1.0],
        winds=[5, 5, 5, 5],
    )
    ics_bytes = generate_ics([forecast], "Munich")
    events = _parse_events(ics_bytes)
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    assert timed, "Expected at least one timed event"
    desc = str(timed[0].get("DESCRIPTION", ""))
    # Should contain aggregated precip with weather emoji (code 61 = 🌧️)
    assert "🌧️" in desc
    assert "7.7mm total" in desc
    # Should contain precip chance range
    assert "50" in desc
    assert "70" in desc
    # Should contain temp range (no cold warning, so 🌡️)
    assert "🌡️" in desc
    assert "°C" in desc


def test_timed_event_description_fahrenheit():
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00"],
        temps=[12, 14],
        codes=[61, 61],
        rain=[50, 60],
        precipitation=[1.5, 2.0],
        winds=[5, 5],
    )
    prefs = {
        "warn_in_allday": 1, "warn_rain": 1, "warn_wind": 1,
        "warn_cold": 1, "warn_snow": 1, "warn_sunny": 0, "cold_threshold": 3.0,
        "show_allday_events": 1, "timed_events_enabled": 1,
        "allday_rain": 1, "allday_wind": 1, "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0,
        "temp_unit": "F",
    }
    ics_bytes = generate_ics([forecast], "Munich", prefs=prefs)
    events = _parse_events(ics_bytes)
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    assert timed
    desc = str(timed[0].get("DESCRIPTION", ""))
    assert "°F" in desc


def test_overlapping_rain_and_cold_produces_single_timed_event():
    """Overlapping rain and cold windows merge into one calendar event."""
    forecast = _make_forecast(
        times=[
            "2026-03-10T17:00", "2026-03-10T18:00", "2026-03-10T19:00",
            "2026-03-10T20:00", "2026-03-10T21:00", "2026-03-10T22:00",
        ],
        temps=[2, 1, 0, -1, -1, -2],
        codes=[61, 61, 63, 63, 61, 61],
        rain=[50, 60, 70, 65, 55, 50],
        precipitation=[1.5, 2.0, 3.0, 2.5, 1.5, 1.0],
        winds=[5, 5, 5, 5, 5, 5],
    )
    prefs = {
        "warn_in_allday": 1, "warn_rain": 1, "warn_wind": 1,
        "warn_cold": 1, "warn_snow": 1, "warn_sunny": 0, "cold_threshold": 3.0,
        "show_allday_events": 1, "timed_events_enabled": 1,
        "allday_rain": 1, "allday_wind": 1, "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0,
    }
    ics_bytes = generate_ics([forecast], "Munich", prefs=prefs)
    events = _parse_events(ics_bytes)
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    # Rain 17-23 and cold 17-23 overlap → single merged event
    assert len(timed) == 1
    summary = str(timed[0]["SUMMARY"])
    assert "☂️" in summary
    assert "🥶" in summary


def test_generate_ics_summary_uses_prefs_cold_threshold():
    forecast = _make_forecast(
        times=["2026-03-10T06:00", "2026-03-10T09:00", "2026-03-10T12:00", "2026-03-10T15:00"],
        temps=[15, 15, 15, 15],
        codes=[1, 1, 2, 2],
        rain=[0, 0, 0, 0],
        winds=[5, 5, 5, 5],
    )
    prefs = {
        "warn_in_allday": 1, "warn_rain": 1, "warn_wind": 1,
        "warn_cold": 1, "warn_snow": 1, "warn_sunny": 0, "cold_threshold": 20.0,
        "show_allday_events": 1, "timed_events_enabled": 1,
        "allday_rain": 1, "allday_wind": 1, "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0,
    }
    ics_bytes = generate_ics([forecast], "Munich", prefs=prefs)
    events = _parse_events(ics_bytes)
    all_day = next(e for e in events if not hasattr(e["DTSTART"].dt, "hour"))
    assert "🥶" in str(all_day["SUMMARY"])


def _parse_alarms(event) -> list:
    return [c for c in event.walk() if c.name == "VALARM"]


def test_allday_event_no_alarm_by_default():
    forecast = _make_forecast(
        times=["2026-03-10T06:00", "2026-03-10T12:00"],
        temps=[10, 15],
        codes=[0, 1],
        rain=[0, 0],
        winds=[5, 5],
    )
    ics_bytes = generate_ics([forecast], "Munich, Germany")
    events = _parse_events(ics_bytes)
    all_day = next(e for e in events if not hasattr(e["DTSTART"].dt, "hour"))
    assert len(_parse_alarms(all_day)) == 0


def test_allday_event_alarm_at_7am():
    forecast = _make_forecast(
        times=["2026-03-10T06:00", "2026-03-10T12:00"],
        temps=[10, 15],
        codes=[0, 1],
        rain=[0, 0],
        winds=[5, 5],
    )
    prefs = {
        "warn_in_allday": 1, "warn_rain": 1, "warn_wind": 1,
        "warn_cold": 1, "warn_snow": 1, "warn_sunny": 0, "cold_threshold": 3.0,
        "show_allday_events": 1, "timed_events_enabled": 1,
        "allday_rain": 1, "allday_wind": 1, "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0,
        "reminder_allday_hour": 7,
    }
    ics_bytes = generate_ics([forecast], "Munich, Germany", prefs=prefs)
    events = _parse_events(ics_bytes)
    all_day = next(e for e in events if not hasattr(e["DTSTART"].dt, "hour"))
    alarms = _parse_alarms(all_day)
    assert len(alarms) == 1
    assert alarms[0]["TRIGGER"].dt == timedelta(hours=7)
    assert str(alarms[0]["ACTION"]) == "DISPLAY"


def test_allday_event_no_alarm_when_minus_one():
    forecast = _make_forecast(
        times=["2026-03-10T06:00", "2026-03-10T12:00"],
        temps=[10, 15],
        codes=[0, 1],
        rain=[0, 0],
        winds=[5, 5],
    )
    prefs = {
        "warn_in_allday": 1, "warn_rain": 1, "warn_wind": 1,
        "warn_cold": 1, "warn_snow": 1, "warn_sunny": 0, "cold_threshold": 3.0,
        "show_allday_events": 1, "timed_events_enabled": 1,
        "allday_rain": 1, "allday_wind": 1, "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0,
        "reminder_allday_hour": -1,
    }
    ics_bytes = generate_ics([forecast], "Munich, Germany", prefs=prefs)
    events = _parse_events(ics_bytes)
    all_day = next(e for e in events if not hasattr(e["DTSTART"].dt, "hour"))
    assert len(_parse_alarms(all_day)) == 0


def test_timed_event_alarm_15_minutes_before():
    forecast = _make_forecast(
        times=[
            "2026-03-10T10:00", "2026-03-10T11:00",
            "2026-03-10T12:00", "2026-03-10T13:00",
        ],
        temps=[12, 12, 13, 13],
        codes=[1, 1, 1, 1],
        rain=[50, 60, 55, 45],
        winds=[5, 5, 5, 5],
        precipitation=[2.0, 3.0, 2.5, 1.0],
    )
    prefs = {
        "warn_in_allday": 1, "warn_rain": 1, "warn_wind": 1,
        "warn_cold": 1, "warn_snow": 1, "warn_sunny": 0, "cold_threshold": 3.0,
        "show_allday_events": 1, "timed_events_enabled": 1,
        "allday_rain": 1, "allday_wind": 1, "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0,
        "reminder_timed_minutes": 15,
    }
    ics_bytes = generate_ics([forecast], "Munich, Germany", prefs=prefs)
    events = _parse_events(ics_bytes)
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    assert len(timed) >= 1
    alarms = _parse_alarms(timed[0])
    assert len(alarms) == 1
    assert alarms[0]["TRIGGER"].dt == timedelta(minutes=-15)


def test_timed_event_no_alarm_by_default():
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00"],
        temps=[12, 12],
        codes=[1, 1],
        rain=[50, 60],
        winds=[5, 5],
        precipitation=[2.0, 3.0],
    )
    ics_bytes = generate_ics([forecast], "Munich, Germany")
    events = _parse_events(ics_bytes)
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    assert len(timed) >= 1
    assert len(_parse_alarms(timed[0])) == 0


def test_allday_event_evening_alarm():
    forecast = _make_forecast(
        times=["2026-03-10T06:00", "2026-03-10T12:00"],
        temps=[10, 15],
        codes=[0, 1],
        rain=[0, 0],
        winds=[5, 5],
    )
    prefs = {
        "warn_in_allday": 1, "warn_rain": 1, "warn_wind": 1,
        "warn_cold": 1, "warn_snow": 1, "warn_sunny": 0, "cold_threshold": 3.0,
        "show_allday_events": 1, "timed_events_enabled": 1,
        "allday_rain": 1, "allday_wind": 1, "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0,
        "reminder_evening_hour": 20,  # 8 PM the day before
    }
    ics_bytes = generate_ics([forecast], "Munich, Germany", prefs=prefs)
    events = _parse_events(ics_bytes)
    all_day = next(e for e in events if not hasattr(e["DTSTART"].dt, "hour"))
    alarms = _parse_alarms(all_day)
    assert len(alarms) == 1
    # 8 PM = 4 hours before midnight = -240 minutes
    assert alarms[0]["TRIGGER"].dt == timedelta(minutes=-240)


def test_allday_event_both_evening_and_morning_alarms():
    forecast = _make_forecast(
        times=["2026-03-10T06:00", "2026-03-10T12:00"],
        temps=[10, 15],
        codes=[0, 1],
        rain=[0, 0],
        winds=[5, 5],
    )
    prefs = {
        "warn_in_allday": 1, "warn_rain": 1, "warn_wind": 1,
        "warn_cold": 1, "warn_snow": 1, "warn_sunny": 0, "cold_threshold": 3.0,
        "show_allday_events": 1, "timed_events_enabled": 1,
        "allday_rain": 1, "allday_wind": 1, "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0,
        "reminder_evening_hour": 19,  # 7 PM
        "reminder_allday_hour": 7,    # 7 AM
    }
    ics_bytes = generate_ics([forecast], "Munich, Germany", prefs=prefs)
    events = _parse_events(ics_bytes)
    all_day = next(e for e in events if not hasattr(e["DTSTART"].dt, "hour"))
    alarms = _parse_alarms(all_day)
    assert len(alarms) == 2
    triggers = sorted([a["TRIGGER"].dt for a in alarms])
    # -300 min = 5 hours before midnight (7 PM), +7 hours after midnight (7 AM)
    assert triggers == [timedelta(minutes=-300), timedelta(hours=7)]


# --- Google active ICS ---

def test_google_active_ics_is_valid():
    ics_bytes = generate_google_active_ics("https://weathercal.app/settings")
    cal = Calendar.from_ical(ics_bytes)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert len(events) == 1


def test_google_active_ics_contains_info_event():
    ics_bytes = generate_google_active_ics("https://weathercal.app/settings")
    cal = Calendar.from_ical(ics_bytes)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    event = events[0]
    assert "Google Calendar" in str(event["SUMMARY"])
    assert "google-active@weathercal.app" == str(event["UID"])
    assert str(event["TRANSP"]) == "TRANSPARENT"


def test_google_active_ics_includes_settings_url():
    url = "https://weathercal.app/settings"
    ics_bytes = generate_google_active_ics(url)
    cal = Calendar.from_ical(ics_bytes)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert url in str(events[0]["DESCRIPTION"])


# --- Cold temp scoping in merged summaries ---


def test_merged_summary_cold_plus_rain_shows_cold_temps_only():
    """Combined cold+rain summary uses only cold-qualifying temps for the range."""
    from src.services.calendar_events import _merged_window_summary
    from src.services.forecast_formatting import MergedWarningWindow
    merged = MergedWarningWindow(
        warning_types=["rain", "cold"], emojis=["☂️", "🥶"],
        start_time="2026-03-10T10:00", end_time="2026-03-10T14:00",
    )
    # Hours: 10=2°C (cold), 11=6°C (not cold), 12=7°C (not cold), 13=1°C (cold)
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00", "2026-03-10T12:00", "2026-03-10T13:00"],
        temps=[2, 6, 7, 1],
        codes=[61, 61, 63, 61],
        rain=[50, 70, 60, 50],
        winds=[5, 5, 5, 5],
        precipitation=[1.0, 1.5, 2.0, 0.8],
    )
    result = _merged_window_summary(merged, forecast)
    # Should show only cold temps (1, 2) → "1 ~ 2°C", not "1 ~ 7°C"
    assert "☂️" in result
    assert "🥶" in result
    assert "1 ~ 2°C" in result


def test_merged_summary_single_cold_temp_no_tilde():
    """When all cold temps round to same value, no ~ in output."""
    from src.services.calendar_events import _merged_window_summary
    from src.services.forecast_formatting import MergedWarningWindow
    merged = MergedWarningWindow(
        warning_types=["rain", "cold"], emojis=["☂️", "🥶"],
        start_time="2026-03-10T10:00", end_time="2026-03-10T13:00",
    )
    # Only one cold hour: 10=2.4°C (rounds to 2), rest are warm
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00", "2026-03-10T12:00"],
        temps=[2.4, 6, 7],
        codes=[61, 61, 63],
        rain=[50, 70, 60],
        winds=[5, 5, 5],
        precipitation=[1.0, 1.5, 2.0],
    )
    result = _merged_window_summary(merged, forecast)
    assert "~" not in result
    assert "2°C" in result


# --- Contextual emoji logic in _format_window_description ---


def test_timed_description_snow_event_has_snowflake_and_cold_emoji():
    """Snow event → ❄️ on precip line, 🥶 on temp line."""
    from src.services.calendar_events import _format_window_description
    from src.services.forecast_formatting import MergedWarningWindow
    window = MergedWarningWindow(
        warning_types=["snow", "cold"], emojis=["❄️", "🥶"],
        start_time="2026-03-10T10:00", end_time="2026-03-10T13:00",
    )
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00", "2026-03-10T12:00"],
        temps=[-2, -1, 0],
        codes=[71, 73, 71],  # snow codes
        rain=[60, 70, 50],
        precipitation=[1.5, 2.0, 1.0],
        winds=[10, 12, 8],
    )
    desc = _format_window_description(forecast, window)
    assert "❄️" in desc          # snowflake on precip line
    assert "🥶" in desc          # cold emoji on temp line
    assert "4.5mm total" in desc  # total precip


def test_timed_description_cold_only_no_precip_line():
    """Cold event with no precipitation → 🥶 temp line, no precip line."""
    from src.services.calendar_events import _format_window_description
    from src.services.forecast_formatting import MergedWarningWindow
    window = MergedWarningWindow(
        warning_types=["cold"], emojis=["🥶"],
        start_time="2026-03-10T06:00", end_time="2026-03-10T10:00",
    )
    forecast = _make_forecast(
        times=["2026-03-10T06:00", "2026-03-10T07:00", "2026-03-10T08:00", "2026-03-10T09:00"],
        temps=[-5, -3, -2, 0],
        codes=[0, 0, 1, 1],
        rain=[0, 0, 0, 0],
        precipitation=[0, 0, 0, 0],
        winds=[5, 5, 5, 5],
    )
    desc = _format_window_description(forecast, window)
    assert "🥶" in desc
    assert "mm" not in desc  # no precip line
    assert "°C" in desc


def test_timed_description_hot_event_has_hot_emoji():
    """Hot event → 🥵 on temp line."""
    from src.services.calendar_events import _format_window_description
    from src.services.forecast_formatting import MergedWarningWindow
    window = MergedWarningWindow(
        warning_types=["hot"], emojis=["🥵"],
        start_time="2026-03-10T12:00", end_time="2026-03-10T16:00",
    )
    forecast = _make_forecast(
        times=["2026-03-10T12:00", "2026-03-10T13:00", "2026-03-10T14:00", "2026-03-10T15:00"],
        temps=[35, 37, 38, 36],
        codes=[0, 0, 1, 1],
        rain=[0, 0, 0, 0],
        precipitation=[0, 0, 0, 0],
        winds=[5, 5, 5, 5],
    )
    desc = _format_window_description(forecast, window)
    assert "🥵" in desc
    assert "°C" in desc
    assert "mm" not in desc


def test_timed_description_rain_not_cold_has_weather_emoji_and_thermometer():
    """Rain event (not cold) → weather code emoji on precip, 🌡️ on temp line."""
    from src.services.calendar_events import _format_window_description
    from src.services.forecast_formatting import MergedWarningWindow
    window = MergedWarningWindow(
        warning_types=["rain"], emojis=["☂️"],
        start_time="2026-03-10T10:00", end_time="2026-03-10T13:00",
    )
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00", "2026-03-10T12:00"],
        temps=[15, 16, 17],
        codes=[61, 61, 63],  # 61 = 🌧️
        rain=[50, 60, 70],
        precipitation=[1.0, 1.5, 2.0],
        winds=[5, 5, 5],
    )
    desc = _format_window_description(forecast, window)
    assert "🌧️" in desc    # weather code emoji for rain
    assert "🌡️" in desc   # thermometer (not cold, not hot)
    assert "°C" in desc
    assert "4.5mm total" in desc


def test_timed_description_wind_event_no_precip():
    """Wind-only event → 💨 line, no precip line."""
    from src.services.calendar_events import _format_window_description
    from src.services.forecast_formatting import MergedWarningWindow
    window = MergedWarningWindow(
        warning_types=["wind"], emojis=["🌬️"],
        start_time="2026-03-10T14:00", end_time="2026-03-10T17:00",
    )
    forecast = _make_forecast(
        times=["2026-03-10T14:00", "2026-03-10T15:00", "2026-03-10T16:00"],
        temps=[18, 19, 17],
        codes=[1, 2, 3],
        rain=[0, 0, 0],
        precipitation=[0, 0, 0],
        winds=[40, 55, 45],
    )
    desc = _format_window_description(forecast, window)
    assert "💨" in desc       # wind emoji
    assert "55 km/h" in desc  # peak gust
    assert "mm" not in desc   # no precip line


def test_timed_description_combined_rain_wind():
    """Combined rain+wind → precip line, wind line, and temp line."""
    from src.services.calendar_events import _format_window_description
    from src.services.forecast_formatting import MergedWarningWindow
    window = MergedWarningWindow(
        warning_types=["rain", "wind"], emojis=["☂️", "🌬️"],
        start_time="2026-03-10T10:00", end_time="2026-03-10T14:00",
    )
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00", "2026-03-10T12:00", "2026-03-10T13:00"],
        temps=[12, 13, 14, 13],
        codes=[61, 63, 65, 61],
        rain=[50, 60, 70, 55],
        precipitation=[1.5, 2.0, 3.0, 1.0],
        winds=[35, 45, 50, 40],
    )
    desc = _format_window_description(forecast, window)
    lines = desc.strip().split("\n")
    assert len(lines) == 3  # precip, wind, temp
    assert "mm total" in lines[0]   # precip line
    assert "💨" in lines[1]         # wind line
    assert "🌡️" in lines[2]       # temp line
    assert "°C" in lines[2]


def test_generate_ics_custom_cal_name():
    forecast = _make_forecast(
        times=["2026-03-10T10:00"],
        temps=[12],
        codes=[0],
        rain=[0],
        winds=[5],
    )
    ics_bytes = generate_ics([forecast], "Munich", cal_name="WeatherCal - Promo")
    assert b"WeatherCal - Promo" in ics_bytes


def test_generate_ics_default_cal_name():
    forecast = _make_forecast(
        times=["2026-03-10T10:00"],
        temps=[12],
        codes=[0],
        rain=[0],
        winds=[5],
    )
    ics_bytes = generate_ics([forecast], "Munich")
    cal = Calendar.from_ical(ics_bytes)
    assert str(cal["X-WR-CALNAME"]) == "WeatherCal"
