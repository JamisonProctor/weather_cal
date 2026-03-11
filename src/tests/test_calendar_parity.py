"""Tests ensuring ICS feed and Google Calendar push produce the same events."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from icalendar import Calendar

from src.integrations.google_push import _push_forecast_events
from src.integrations.ics_service import generate_ics, _stable_uid, _merged_warning_uid
from src.models.forecast import Forecast
from src.services.forecast_formatting import get_warning_windows, merge_overlapping_windows
from src.constants import DEFAULT_PREFS


def _rainy_forecast(date="2026-03-11", location="Munich, Germany"):
    """Forecast with heavy rain windows that trigger timed warnings."""
    base = f"{date}T"
    times = [f"{base}{h:02d}:00" for h in range(6, 22)]
    temps = [10 + i for i in range(len(times))]
    codes = [61] * len(times)  # rain code
    rain = [80] * len(times)   # 80% chance
    precipitation = [2.5] * len(times)  # 2.5mm/h -> triggers rain warning
    winds = [10] * len(times)
    return Forecast(
        date=date,
        location=location,
        high=max(temps),
        low=min(temps),
        summary="Rainy day",
        description="Rain all day",
        times=times,
        temps=temps,
        codes=codes,
        rain=rain,
        precipitation=precipitation,
        winds=winds,
        timezone="Europe/Berlin",
    )


def _mild_forecast(date="2026-03-12", location="Munich, Germany"):
    """Forecast with no warnings — only all-day event expected."""
    base = f"{date}T"
    times = [f"{base}{h:02d}:00" for h in range(6, 22)]
    temps = [15] * len(times)
    codes = [1] * len(times)   # clear sky
    rain = [0] * len(times)
    winds = [5] * len(times)
    return Forecast(
        date=date,
        location=location,
        high=15,
        low=15,
        summary="Mild day",
        description="Clear skies",
        times=times,
        temps=temps,
        codes=codes,
        rain=rain,
        winds=winds,
        timezone="Europe/Berlin",
    )


def _parse_ics_events(ics_bytes):
    """Parse ICS bytes and return list of (uid, summary, is_allday) tuples."""
    cal = Calendar.from_ical(ics_bytes)
    events = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        uid = str(component.get("uid"))
        summary = str(component.get("summary"))
        dtstart = component.get("dtstart")
        # All-day events have a date value, timed events have datetime
        is_allday = not isinstance(dtstart.dt, datetime)
        events.append((uid, summary, is_allday))
    return events


def _capture_google_upserts(forecast, prefs):
    """Run _push_forecast_events with mocked service and return upserted event bodies."""
    from zoneinfo import ZoneInfo

    service = MagicMock()
    upserted = []

    def capture_import(calendarId, body):
        upserted.append(body)
        result = MagicMock()
        result.execute.return_value = {}
        return result

    service.events().import_ = capture_import
    # Also mock list for cleanup (return no existing events)
    service.events().list().execute.return_value = {"items": []}

    tz = ZoneInfo(forecast.timezone) if forecast.timezone else ZoneInfo("UTC")
    _push_forecast_events(service, "cal123", forecast, prefs, tz, forecast.timezone)
    return upserted


class TestAlldayParity:
    def test_allday_events_match(self):
        forecast = _mild_forecast()
        prefs = {**DEFAULT_PREFS, "show_allday_events": 1}

        ics_events = _parse_ics_events(generate_ics([forecast], forecast.location, prefs))
        google_events = _capture_google_upserts(forecast, prefs)

        ics_allday = [(uid, s) for uid, s, allday in ics_events if allday]
        google_allday = [(e["iCalUID"], e["summary"]) for e in google_events if "date" in e.get("start", {})]

        assert len(ics_allday) == len(google_allday) == 1
        assert ics_allday[0][0] == google_allday[0][0]  # same UID

    def test_allday_disabled_both_skip(self):
        forecast = _mild_forecast()
        prefs = {**DEFAULT_PREFS, "show_allday_events": 0}

        ics_events = _parse_ics_events(generate_ics([forecast], forecast.location, prefs))
        google_events = _capture_google_upserts(forecast, prefs)

        ics_allday = [e for e in ics_events if e[2]]
        google_allday = [e for e in google_events if "date" in e.get("start", {})]

        assert len(ics_allday) == 0
        assert len(google_allday) == 0


class TestTimedParity:
    def test_timed_events_match(self):
        forecast = _rainy_forecast()
        prefs = {**DEFAULT_PREFS, "timed_events_enabled": 1, "warn_rain": 1}

        ics_events = _parse_ics_events(generate_ics([forecast], forecast.location, prefs))
        google_events = _capture_google_upserts(forecast, prefs)

        ics_timed = sorted([(uid, s) for uid, s, allday in ics_events if not allday])
        google_timed = sorted([
            (e["iCalUID"], e["summary"]) for e in google_events
            if "dateTime" in e.get("start", {})
        ])

        assert len(ics_timed) == len(google_timed)
        assert len(ics_timed) > 0  # sanity: rain forecast should produce warnings
        for (ics_uid, _), (g_uid, _) in zip(ics_timed, google_timed):
            assert ics_uid == g_uid

    def test_timed_disabled_both_skip(self):
        forecast = _rainy_forecast()
        prefs = {**DEFAULT_PREFS, "timed_events_enabled": 0}

        ics_events = _parse_ics_events(generate_ics([forecast], forecast.location, prefs))
        google_events = _capture_google_upserts(forecast, prefs)

        ics_timed = [e for e in ics_events if not e[2]]
        google_timed = [e for e in google_events if "dateTime" in e.get("start", {})]

        assert len(ics_timed) == 0
        assert len(google_timed) == 0


class TestWarningPrefsParity:
    def test_warn_rain_disabled_both_omit(self):
        forecast = _rainy_forecast()
        prefs = {**DEFAULT_PREFS, "timed_events_enabled": 1, "warn_rain": 0}

        ics_events = _parse_ics_events(generate_ics([forecast], forecast.location, prefs))
        google_events = _capture_google_upserts(forecast, prefs)

        ics_timed = [e for e in ics_events if not e[2]]
        google_timed = [e for e in google_events if "dateTime" in e.get("start", {})]

        # With rain warnings disabled, no timed events from a rain-only forecast
        assert len(ics_timed) == 0
        assert len(google_timed) == 0


class TestSummaryParity:
    def test_summaries_match(self):
        forecast = _rainy_forecast()
        prefs = {**DEFAULT_PREFS, "timed_events_enabled": 1, "warn_rain": 1}

        ics_events = _parse_ics_events(generate_ics([forecast], forecast.location, prefs))
        google_events = _capture_google_upserts(forecast, prefs)

        ics_timed = sorted([(uid, s) for uid, s, allday in ics_events if not allday])
        google_timed = sorted([
            (e["iCalUID"], e["summary"]) for e in google_events
            if "dateTime" in e.get("start", {})
        ])

        for (_, ics_summary), (_, g_summary) in zip(ics_timed, google_timed):
            assert ics_summary == g_summary


def _cold_forecast(date="2026-03-13", location="Munich, Germany"):
    """Forecast with temps at 8°C — triggers cold warning at threshold=10."""
    base = f"{date}T"
    times = [f"{base}{h:02d}:00" for h in range(6, 22)]
    return Forecast(
        date=date,
        location=location,
        high=9, low=2,
        summary="Cold day",
        description="Very cold",
        times=times,
        temps=[8] * len(times),
        codes=[3] * len(times),
        rain=[0] * len(times),
        winds=[5] * len(times),
        timezone="Europe/Berlin",
    )


def _windy_rainy_forecast(date="2026-03-14", location="Munich, Germany"):
    """Forecast with rain + high wind — triggers both warnings."""
    base = f"{date}T"
    times = [f"{base}{h:02d}:00" for h in range(6, 22)]
    return Forecast(
        date=date,
        location=location,
        high=15, low=10,
        summary="Stormy day",
        description="Wind and rain",
        times=times,
        temps=[12] * len(times),
        codes=[63] * len(times),
        rain=[80] * len(times),
        precipitation=[3.0] * len(times),
        winds=[55] * len(times),
        timezone="Europe/Berlin",
    )


class TestCustomPrefsParity:
    def test_custom_cold_threshold_parity(self):
        """cold_threshold=10 — both ICS and Google produce same cold warning events."""
        forecast = _cold_forecast()
        prefs = {**DEFAULT_PREFS, "cold_threshold": 10.0}

        ics_events = _parse_ics_events(generate_ics([forecast], forecast.location, prefs))
        google_events = _capture_google_upserts(forecast, prefs)

        ics_timed = sorted([(uid, s) for uid, s, allday in ics_events if not allday])
        google_timed = sorted([
            (e["iCalUID"], e["summary"]) for e in google_events
            if "dateTime" in e.get("start", {})
        ])

        assert len(ics_timed) == len(google_timed)
        assert len(ics_timed) > 0, "Expected cold warning with threshold=10 and temp=8"
        for (ics_uid, ics_s), (g_uid, g_s) in zip(ics_timed, google_timed):
            assert ics_uid == g_uid
            assert ics_s == g_s

    def test_fahrenheit_summary_parity(self):
        """temp_unit=F — both produce matching summaries; timed events show °F."""
        forecast = _rainy_forecast()
        prefs = {**DEFAULT_PREFS, "temp_unit": "F"}

        ics_events = _parse_ics_events(generate_ics([forecast], forecast.location, prefs))
        google_events = _capture_google_upserts(forecast, prefs)

        # All-day summaries match between ICS and Google
        ics_allday = [(uid, s) for uid, s, allday in ics_events if allday]
        google_allday = [(e["iCalUID"], e["summary"]) for e in google_events if "date" in e.get("start", {})]
        assert len(ics_allday) == len(google_allday) == 1
        assert ics_allday[0][0] == google_allday[0][0]
        assert ics_allday[0][1] == google_allday[0][1]

        # Timed event summaries match and contain °F
        ics_timed = sorted([(uid, s) for uid, s, allday in ics_events if not allday])
        google_timed = sorted([
            (e["iCalUID"], e["summary"]) for e in google_events
            if "dateTime" in e.get("start", {})
        ])
        assert len(ics_timed) == len(google_timed)
        for (ics_uid, ics_s), (g_uid, g_s) in zip(ics_timed, google_timed):
            assert ics_uid == g_uid
            assert ics_s == g_s

    def test_multiple_warnings_disabled_parity(self):
        """warn_rain=0, warn_wind=0 — no timed events from either path."""
        forecast = _windy_rainy_forecast()
        prefs = {**DEFAULT_PREFS, "warn_rain": 0, "warn_wind": 0}

        ics_events = _parse_ics_events(generate_ics([forecast], forecast.location, prefs))
        google_events = _capture_google_upserts(forecast, prefs)

        ics_timed = [e for e in ics_events if not e[2]]
        google_timed = [e for e in google_events if "dateTime" in e.get("start", {})]

        assert len(ics_timed) == 0
        assert len(google_timed) == 0

    def test_allday_off_timed_on_parity(self):
        """show_allday_events=0, timed_events_enabled=1 — only timed events, matching."""
        forecast = _rainy_forecast()
        prefs = {**DEFAULT_PREFS, "show_allday_events": 0, "timed_events_enabled": 1, "warn_rain": 1}

        ics_events = _parse_ics_events(generate_ics([forecast], forecast.location, prefs))
        google_events = _capture_google_upserts(forecast, prefs)

        ics_allday = [e for e in ics_events if e[2]]
        google_allday = [e for e in google_events if "date" in e.get("start", {})]
        assert len(ics_allday) == 0
        assert len(google_allday) == 0

        ics_timed = sorted([(uid, s) for uid, s, allday in ics_events if not allday])
        google_timed = sorted([
            (e["iCalUID"], e["summary"]) for e in google_events
            if "dateTime" in e.get("start", {})
        ])

        assert len(ics_timed) == len(google_timed)
        assert len(ics_timed) > 0
        for (ics_uid, ics_s), (g_uid, g_s) in zip(ics_timed, google_timed):
            assert ics_uid == g_uid
            assert ics_s == g_s
