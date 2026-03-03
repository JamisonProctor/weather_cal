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
    assert "Rain Warning" in str(timed["SUMMARY"])
    assert "☂️" in str(timed["SUMMARY"])

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
    }
    ics_bytes = generate_ics([forecast], "Munich, Germany", prefs=prefs)
    events = _parse_events(ics_bytes)
    timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
    assert any("Sunny" in str(e["SUMMARY"]) for e in timed)


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
    }
    ics_bytes = generate_ics([forecast], "Munich, Germany", prefs=prefs)
    events = _parse_events(ics_bytes)
    all_day = next(e for e in events if not hasattr(e["DTSTART"].dt, "hour"))
    assert "🥶" in str(all_day["SUMMARY"])
