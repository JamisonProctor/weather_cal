from icalendar import Calendar

from src.integrations.ics_service import generate_ics
from src.models.forecast import Forecast


def _parse_events(ics_bytes: bytes) -> list:
    cal = Calendar.from_ical(ics_bytes)
    return [c for c in cal.walk() if c.name == "VEVENT"]


def _make_forecast(date="2026-03-10", location="Munich, Germany", timezone="Europe/Berlin", **kwargs):
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
    ics_bytes = generate_ics([forecast], "Munich, Germany")
    events = _parse_events(ics_bytes)

    assert len(events) == 1
    assert str(events[0]["SUMMARY"]) == forecast.summary
    # All-day event has a date (not datetime) as DTSTART
    assert not hasattr(events[0]["DTSTART"].dt, "hour")


def test_warning_produces_timed_event():
    # Rain probability >= 40% for a block of hours → Rain Warning
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
        winds=[5, 5, 5, 5],
    )
    ics_bytes = generate_ics([forecast], "Munich, Germany")
    events = _parse_events(ics_bytes)

    # One all-day + one timed warning
    assert len(events) == 2

    timed = next(e for e in events if hasattr(e["DTSTART"].dt, "hour"))
    summary = str(timed["SUMMARY"])
    assert "☂️" in summary
    assert "%" in summary  # contextual rain probability

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
        winds=[5, 5],
    )

    ics1 = generate_ics([forecast], "Munich, Germany")
    ics2 = generate_ics([forecast], "Munich, Germany")

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
        winds=[5, 5],
    )
    prefs = {
        "warn_in_allday": 1, "warn_rain": 0, "warn_wind": 1,
        "warn_cold": 1, "warn_snow": 1, "warn_sunny": 0, "cold_threshold": 3.0,
        "show_allday_events": 1, "timed_events_enabled": 1,
        "allday_rain": 1, "allday_wind": 1, "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0,
    }
    ics_bytes = generate_ics([forecast], "Munich, Germany", prefs=prefs)
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
    ics_bytes = generate_ics([forecast], "Munich, Germany", prefs=prefs)
    events = _parse_events(ics_bytes)
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    sunny = [e for e in timed if "☀️" in str(e["SUMMARY"])]
    assert len(sunny) == 1
    summary = str(sunny[0]["SUMMARY"])
    assert "°C" in summary
    assert " ~ " in summary


def test_x_published_ttl_present():
    forecast = _make_forecast()
    ics_bytes = generate_ics([forecast], "Munich, Germany")
    assert b"X-PUBLISHED-TTL:PT12H" in ics_bytes


def test_allday_event_description_contains_settings_url():
    forecast = _make_forecast(description="Nice day")
    settings_url = "https://weathercal.app/settings"
    ics_bytes = generate_ics([forecast], "Munich, Germany", settings_url=settings_url)
    events = _parse_events(ics_bytes)
    all_day = next(e for e in events if not hasattr(e["DTSTART"].dt, "hour"))
    description = str(all_day.get("DESCRIPTION", ""))
    assert "Change your settings:" in description
    assert settings_url in description


def test_timed_event_description_contains_settings_url():
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00"],
        temps=[12, 12],
        codes=[61, 61],
        rain=[70, 70],
        winds=[5, 5],
    )
    settings_url = "https://weathercal.app/settings"
    ics_bytes = generate_ics([forecast], "Munich, Germany", settings_url=settings_url)
    events = _parse_events(ics_bytes)
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    assert timed, "Expected at least one timed warning event"
    description = str(timed[0].get("DESCRIPTION", ""))
    assert "Change your settings:" in description
    assert settings_url in description


def test_vtimezone_present_when_timed_events_exist():
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00"],
        temps=[12, 12],
        codes=[1, 1],
        rain=[50, 60],
        winds=[5, 5],
    )
    ics_bytes = generate_ics([forecast], "Munich, Germany")
    cal = Calendar.from_ical(ics_bytes)
    vtimezones = [c for c in cal.walk() if c.name == "VTIMEZONE"]
    assert len(vtimezones) >= 1
    tzids = {str(vtz["TZID"]) for vtz in vtimezones}
    assert "Europe/Berlin" in tzids


def test_generate_ics_skips_invalid_date():
    forecast = _make_forecast(date="not-a-date")
    ics_bytes = generate_ics([forecast], "Munich, Germany")
    events = _parse_events(ics_bytes)
    assert len(events) == 0


def test_generate_ics_both_allday_and_timed_disabled():
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00"],
        temps=[12, 12],
        codes=[61, 61],
        rain=[70, 70],
        winds=[5, 5],
    )
    prefs = {
        "show_allday_events": 0, "timed_events_enabled": 0,
        "warn_in_allday": 1, "warn_rain": 1, "warn_wind": 1,
        "warn_cold": 1, "warn_snow": 1, "warn_sunny": 0, "cold_threshold": 3.0,
        "allday_rain": 1, "allday_wind": 1, "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0,
    }
    ics_bytes = generate_ics([forecast], "Munich, Germany", prefs=prefs)
    events = _parse_events(ics_bytes)
    assert len(events) == 0


def test_generate_ics_unknown_timezone_falls_back_to_utc():
    forecast = _make_forecast(
        timezone="Fake/NoSuchZone",
        times=["2026-03-10T10:00", "2026-03-10T11:00"],
        temps=[12, 12],
        codes=[61, 61],
        rain=[70, 70],
        winds=[5, 5],
    )
    ics_bytes = generate_ics([forecast], "Munich, Germany")
    events = _parse_events(ics_bytes)
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    assert len(timed) >= 1
    # The fallback is timezone.utc, but icalendar may represent it as ZoneInfo('UTC')
    # Either way, the offset should be zero
    assert timed[0]["DTSTART"].dt.utcoffset().total_seconds() == 0


def test_merged_window_summary_sunny_fahrenheit():
    from src.integrations.ics_service import _merged_window_summary
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


def test_merged_window_summary_rain_shows_probability():
    from src.integrations.ics_service import _merged_window_summary
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
        winds=[5, 5, 5],
    )
    result = _merged_window_summary(merged, forecast)
    assert "☂️" in result
    assert "50 ~ 70%" in result


def test_merged_window_summary_wind_shows_speed():
    from src.integrations.ics_service import _merged_window_summary
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
    assert "35 ~ 45 km/h" in result


def test_merged_window_summary_combined_shows_temp():
    from src.integrations.ics_service import _merged_window_summary
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
    from src.integrations.ics_service import _stable_uid
    uid1 = _stable_uid("2026-03-10", "Munich, Germany")
    uid2 = _stable_uid("2026-03-10", "Munich, Germany")
    uid3 = _stable_uid("2026-03-11", "Munich, Germany")
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
        winds=[5, 5, 5, 5],
    )
    ics_bytes = generate_ics([forecast], "Munich, Germany")
    events = _parse_events(ics_bytes)
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    assert timed, "Expected at least one timed event"
    desc = str(timed[0].get("DESCRIPTION", ""))
    # Should contain hourly lines
    assert "10:00" in desc
    assert "11:00" in desc
    assert "12:00" in desc
    assert "13:00" in desc
    # Should contain temp values
    assert "°C" in desc
    # Should contain rain indicator for high rain
    assert "💧" in desc
    # Should contain high/low summary
    assert "High:" in desc
    assert "Low:" in desc


def test_timed_event_description_fahrenheit():
    forecast = _make_forecast(
        times=["2026-03-10T10:00", "2026-03-10T11:00"],
        temps=[12, 14],
        codes=[61, 61],
        rain=[50, 60],
        winds=[5, 5],
    )
    prefs = {
        "warn_in_allday": 1, "warn_rain": 1, "warn_wind": 1,
        "warn_cold": 1, "warn_snow": 1, "warn_sunny": 0, "cold_threshold": 3.0,
        "show_allday_events": 1, "timed_events_enabled": 1,
        "allday_rain": 1, "allday_wind": 1, "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0,
        "temp_unit": "F",
    }
    ics_bytes = generate_ics([forecast], "Munich, Germany", prefs=prefs)
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
        winds=[5, 5, 5, 5, 5, 5],
    )
    prefs = {
        "warn_in_allday": 1, "warn_rain": 1, "warn_wind": 1,
        "warn_cold": 1, "warn_snow": 1, "warn_sunny": 0, "cold_threshold": 3.0,
        "show_allday_events": 1, "timed_events_enabled": 1,
        "allday_rain": 1, "allday_wind": 1, "allday_cold": 1, "allday_snow": 1, "allday_sunny": 0,
    }
    ics_bytes = generate_ics([forecast], "Munich, Germany", prefs=prefs)
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
    ics_bytes = generate_ics([forecast], "Munich, Germany", prefs=prefs)
    events = _parse_events(ics_bytes)
    all_day = next(e for e in events if not hasattr(e["DTSTART"].dt, "hour"))
    assert "🥶" in str(all_day["SUMMARY"])
