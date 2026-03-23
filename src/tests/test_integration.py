"""Integration tests exercising real component boundaries end-to-end."""

import sqlite3
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from icalendar import Calendar

from src.events.db import get_future_events
from src.events.ics_events import build_event_ics
from src.events.store import store_events
from src.integrations.google_push import _push_forecast_events
from src.integrations.ics_service import generate_ics
from src.models.forecast import Forecast
from src.services.calendar_events import build_calendar_events
from src.services.forecast_store import ForecastStore
from src.web.db import (
    DEFAULT_PREFS,
    create_feed_token,
    create_user,
    get_feed_token_by_user,
    get_user_preferences,
    resolve_prefs,
    set_user_location,
    upsert_user_preferences,
)


def _parse_vevents(ics_bytes):
    cal = Calendar.from_ical(ics_bytes)
    return [c for c in cal.walk() if c.name == "VEVENT"]


@pytest.mark.integration
class TestWeatherPipeline:
    def test_store_to_ics(self, db_path):
        """Upsert forecasts → generate_ics → parse → validate VEVENTs."""
        store = ForecastStore(db_path=db_path)
        store.upsert_forecast(Forecast(
            date="2099-06-01",
            location="Munich",
            high=25, low=14,
            summary="☀️ Sunny",
            description="Clear skies all day",
            times=["2099-06-01T10:00", "2099-06-01T11:00", "2099-06-01T12:00"],
            temps=[20, 22, 25],
            codes=[0, 0, 1],
            rain=[0, 0, 0],
            winds=[5, 8, 6],
            timezone="Europe/Berlin",
        ))
        store.upsert_forecast(Forecast(
            date="2099-06-02",
            location="Munich",
            high=18, low=10,
            summary="☂️ Rainy",
            description="Rain expected",
            times=["2099-06-02T10:00", "2099-06-02T11:00", "2099-06-02T12:00"],
            temps=[12, 13, 14],
            codes=[61, 61, 63],
            rain=[50, 60, 70],
            precipitation=[1.5, 2.0, 3.0],
            winds=[5, 5, 5],
            timezone="Europe/Berlin",
        ))

        forecasts = store.get_forecasts_future()
        assert len(forecasts) >= 2

        ics_bytes = generate_ics(forecasts, "Munich")
        events = _parse_vevents(ics_bytes)

        # At minimum: 2 all-day events + 1 rain warning
        assert len(events) >= 3
        summaries = [str(e["SUMMARY"]) for e in events]
        assert any("☀️" in s for s in summaries)
        assert any("☂️" in s for s in summaries)

        # Verify UID stability
        ics_bytes2 = generate_ics(forecasts, "Munich")
        events2 = _parse_vevents(ics_bytes2)
        uids1 = {str(e["UID"]) for e in events}
        uids2 = {str(e["UID"]) for e in events2}
        assert uids1 == uids2


@pytest.mark.integration
class TestEventPipeline:
    def test_store_to_ics(self, db_path):
        """store_events → get_future_events → build_event_ics → validate."""
        future = (datetime.now() + timedelta(days=5)).isoformat()
        events_data = [
            {
                "title": "Jazz Night",
                "start_time": future,
                "end_time": future,
                "location": "Jazzbar Munich",
                "description": "Free live jazz",
                "source_url": "https://example.com/jazz",
                "category": "concert",
                "is_paid": False,
            },
            {
                "title": "Art Opening",
                "start_time": future,
                "end_time": future,
                "location": "Gallery Munich",
                "description": "New exhibition",
                "source_url": "https://example.com/art",
                "category": "exhibition",
                "is_paid": False,
            },
        ]

        result = store_events(db_path, events_data, datetime.now())
        assert result["created"] == 2

        db_events = get_future_events(db_path)
        assert len(db_events) >= 2

        ics_bytes = build_event_ics(db_events)
        vevents = _parse_vevents(ics_bytes)
        assert len(vevents) >= 2

        titles = {str(e["SUMMARY"]) for e in vevents}
        assert "Jazz Night" in titles
        assert "Art Opening" in titles

        # Verify UIDs end with @planz
        for e in vevents:
            assert str(e["UID"]).endswith("@planz")


@pytest.mark.integration
class TestUserLifecycle:
    def test_signup_to_feed(self, db_path):
        """create_user → set_location → create_feed_token → upsert forecasts → generate_ics."""
        user_id = create_user(db_path, "lifecycle@example.com", "supersecretpass1")
        set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
        token = create_feed_token(db_path, user_id)
        assert token is not None

        store = ForecastStore(db_path=db_path)
        store.upsert_forecast(Forecast(
            date="2099-01-01",
            location="Munich",
            high=10, low=2,
            summary="Test",
            description="Test forecast",
            times=["2099-01-01T12:00"],
            temps=[10], codes=[1], rain=[0], winds=[5],
            timezone="Europe/Berlin",
        ))

        forecasts = store.get_forecasts_future()
        assert len(forecasts) >= 1

        ics_bytes = generate_ics(forecasts, "Munich")
        events = _parse_vevents(ics_bytes)
        assert len(events) >= 1

    def test_event_feed_lifecycle(self, db_path):
        """create_user → create_feed_token → store_events → resolve token → build_event_ics."""
        from src.events.db import get_user_id_by_feed_token

        user_id = create_user(db_path, "eventfeed@example.com", "supersecretpass1")
        token = create_feed_token(db_path, user_id)

        future = (datetime.now() + timedelta(days=3)).isoformat()
        store_events(db_path, [
            {
                "title": "User Event",
                "start_time": future,
                "end_time": future,
                "location": "Munich",
                "description": "Test",
                "source_url": "https://example.com/user-event",
                "category": "other",
                "is_paid": False,
            },
        ], datetime.now())

        resolved_user_id = get_user_id_by_feed_token(db_path, token)
        assert resolved_user_id == user_id

        db_events = get_future_events(db_path)
        ics_bytes = build_event_ics(db_events)
        vevents = _parse_vevents(ics_bytes)
        assert len(vevents) >= 1
        assert any("User Event" in str(e["SUMMARY"]) for e in vevents)


@pytest.mark.integration
class TestFeedRoutesE2E:
    def test_weather_feed_route(self, client, db_path, auth_cookies):
        """Full HTTP: create user → set location → insert forecasts → GET weather.ics → validate."""
        user_id, _ = auth_cookies()
        set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
        token = create_feed_token(db_path, user_id)

        store = ForecastStore(db_path=db_path)
        store.upsert_forecast(Forecast(
            date="2099-01-01",
            location="Munich",
            high=10, low=2,
            summary="E2E Test",
            description="End-to-end test forecast",
            times=["2099-01-01T12:00"],
            temps=[10], codes=[1], rain=[0], winds=[5],
            timezone="Europe/Berlin",
        ))

        resp = client.get(f"/feed/{token}/weather.ics")
        assert resp.status_code == 200
        assert "text/calendar" in resp.headers["content-type"]

        vevents = _parse_vevents(resp.content)
        assert len(vevents) >= 1
        # All-day event should have a date-based DTSTART (no hour)
        allday = [e for e in vevents if not hasattr(e["DTSTART"].dt, "hour")]
        assert len(allday) >= 1

    def test_event_feed_route(self, client, db_path, insert_event):
        """Full HTTP: insert events → GET /events.ics → validate ICS."""
        insert_event(title="E2E Concert", category="concert")
        insert_event(title="E2E Market", category="market", external_key="e2e-market-1")

        resp = client.get("/events.ics")
        assert resp.status_code == 200
        assert "text/calendar" in resp.headers["content-type"]

        vevents = _parse_vevents(resp.content)
        titles = {str(e["SUMMARY"]) for e in vevents}
        assert "E2E Concert" in titles
        assert "E2E Market" in titles


def _rainy_forecast(date="2099-06-15"):
    """Forecast with heavy rain that triggers timed warnings."""
    base = f"{date}T"
    times = [f"{base}{h:02d}:00" for h in range(6, 22)]
    return Forecast(
        date=date,
        location="Munich",
        high=20, low=10,
        summary="Rainy day",
        description="Rain all day",
        times=times,
        temps=[12 + i for i in range(len(times))],
        codes=[61] * len(times),
        rain=[80] * len(times),
        precipitation=[2.5] * len(times),
        winds=[10] * len(times),
        timezone="Europe/Berlin",
    )


def _cold_forecast(date="2099-01-15"):
    """Forecast with cold temps that trigger cold warnings at threshold=10."""
    base = f"{date}T"
    times = [f"{base}{h:02d}:00" for h in range(6, 22)]
    return Forecast(
        date=date,
        location="Munich",
        high=9, low=2,
        summary="Cold day",
        description="Very cold",
        times=times,
        temps=[8] * len(times),  # 8°C, below threshold of 10
        codes=[3] * len(times),
        rain=[0] * len(times),
        winds=[5] * len(times),
        timezone="Europe/Berlin",
    )


def _capture_google_upserts(forecast, prefs):
    """Run _push_forecast_events with mocked service, return upserted event bodies."""
    from zoneinfo import ZoneInfo
    service = MagicMock()
    upserted = []

    def capture_import(calendarId, body):
        upserted.append(body)
        result = MagicMock()
        result.execute.return_value = {}
        return result

    service.events().import_ = capture_import
    service.events().list().execute.return_value = {"items": []}

    tz = ZoneInfo(forecast.timezone) if forecast.timezone else ZoneInfo("UTC")
    _push_forecast_events(service, "cal123", forecast, prefs, tz, forecast.timezone)
    return upserted


@pytest.mark.integration
class TestPrefsToCalendar:
    """Tests verifying the full save→load→generate round-trip for preferences."""

    def test_allday_disabled_roundtrip_ics(self, db_path):
        """Save show_allday_events=0 → generate ICS → no all-day VEVENT."""
        user_id = create_user(db_path, "allday-off@example.com", "supersecretpass1")
        upsert_user_preferences(db_path, user_id, cold_threshold=3.0,
                                warn_in_allday=1, warn_rain=1, warn_wind=1,
                                warn_cold=1, warn_snow=1, warn_sunny=1,
                                show_allday_events=0)
        prefs = resolve_prefs(get_user_preferences(db_path, user_id))

        forecast = _rainy_forecast()
        ics_bytes = generate_ics([forecast], forecast.location, prefs)
        events = _parse_vevents(ics_bytes)

        allday = [e for e in events if not hasattr(e["DTSTART"].dt, "hour")]
        assert len(allday) == 0

    def test_allday_disabled_roundtrip_google(self, db_path):
        """Save show_allday_events=0 → mock Google push → no all-day event upserted."""
        user_id = create_user(db_path, "allday-off-g@example.com", "supersecretpass1")
        upsert_user_preferences(db_path, user_id, cold_threshold=3.0,
                                warn_in_allday=1, warn_rain=1, warn_wind=1,
                                warn_cold=1, warn_snow=1, warn_sunny=1,
                                show_allday_events=0)
        prefs = resolve_prefs(get_user_preferences(db_path, user_id))

        forecast = _rainy_forecast()
        google_events = _capture_google_upserts(forecast, prefs)

        allday = [e for e in google_events if "date" in e.get("start", {})]
        assert len(allday) == 0

    def test_timed_disabled_roundtrip_ics(self, db_path):
        """Save timed_events_enabled=0 → ICS with rainy forecast → no timed VEVENTs."""
        user_id = create_user(db_path, "timed-off@example.com", "supersecretpass1")
        upsert_user_preferences(db_path, user_id, cold_threshold=3.0,
                                warn_in_allday=1, warn_rain=1, warn_wind=1,
                                warn_cold=1, warn_snow=1, warn_sunny=1,
                                timed_events_enabled=0)
        prefs = resolve_prefs(get_user_preferences(db_path, user_id))

        forecast = _rainy_forecast()
        ics_bytes = generate_ics([forecast], forecast.location, prefs)
        events = _parse_vevents(ics_bytes)

        timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
        assert len(timed) == 0

    def test_custom_cold_threshold_roundtrip(self, db_path):
        """Save cold_threshold=10 → ICS with 8°C forecast → cold warning appears."""
        user_id = create_user(db_path, "cold-thresh@example.com", "supersecretpass1")
        upsert_user_preferences(db_path, user_id, cold_threshold=10.0,
                                warn_in_allday=1, warn_rain=1, warn_wind=1,
                                warn_cold=1, warn_snow=1, warn_sunny=1)
        prefs = resolve_prefs(get_user_preferences(db_path, user_id))

        forecast = _cold_forecast()
        ics_bytes = generate_ics([forecast], forecast.location, prefs)
        events = _parse_vevents(ics_bytes)

        timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
        assert len(timed) > 0, "Expected cold warning timed events with threshold=10 and temp=8"

    def test_fahrenheit_roundtrip(self, db_path):
        """Save temp_unit=F → ICS → timed summaries show °F (all-day uses bare °)."""
        user_id = create_user(db_path, "fahr@example.com", "supersecretpass1")
        upsert_user_preferences(db_path, user_id, cold_threshold=3.0,
                                warn_in_allday=1, warn_rain=1, warn_wind=1,
                                warn_cold=1, warn_snow=1, warn_sunny=1,
                                temp_unit="F")
        prefs = resolve_prefs(get_user_preferences(db_path, user_id))

        forecast = _rainy_forecast()
        ics_bytes = generate_ics([forecast], forecast.location, prefs)
        events = _parse_vevents(ics_bytes)

        # Timed events (rain warnings) show °F in their summaries
        timed = [e for e in events if hasattr(e["DTSTART"].dt, "hour")]
        assert len(timed) > 0
        assert "°F" in str(timed[0]["DESCRIPTION"])

    def test_zero_prefs_survive_resolve(self, db_path):
        """Save show_allday_events=0 → get_user_preferences → resolve_prefs → value is still 0."""
        user_id = create_user(db_path, "zero-prefs@example.com", "supersecretpass1")
        upsert_user_preferences(db_path, user_id, cold_threshold=3.0,
                                warn_in_allday=1, warn_rain=1, warn_wind=1,
                                warn_cold=1, warn_snow=1, warn_sunny=1,
                                show_allday_events=0)
        prefs_row = get_user_preferences(db_path, user_id)
        prefs = resolve_prefs(prefs_row)
        assert prefs["show_allday_events"] == 0

    def test_settings_post_to_feed_e2e(self, client, db_path, auth_cookies):
        """Full HTTP: POST /settings with show_allday_events unchecked → GET feed → no all-day event."""
        user_id, auth = auth_cookies()
        set_user_location(db_path, user_id, "Munich", 48.137, 11.576, "Europe/Berlin")
        token = create_feed_token(db_path, user_id)

        store = ForecastStore(db_path=db_path)
        store.upsert_forecast(Forecast(
            date="2099-01-01",
            location="Munich",
            high=10, low=2,
            summary="Test",
            description="Test forecast",
            times=["2099-01-01T12:00"],
            temps=[10], codes=[1], rain=[0], winds=[5],
            timezone="Europe/Berlin",
        ))

        # POST settings with show_allday_events unchecked (not sent = off)
        resp = auth.post("/settings", data={
            "cold_threshold": "3.0",
            "warm_threshold": "14.0",
            "hot_threshold": "28.0",
            "temp_unit": "C",
            "warn_in_allday": "on",
            "warn_rain": "on",
            "warn_wind": "on",
            "warn_cold": "on",
            "warn_snow": "on",
            "warn_sunny": "on",
            "warn_hot": "on",
            "timed_events_enabled": "on",
            # show_allday_events NOT included = unchecked = 0
        })
        assert resp.status_code == 303

        # GET feed and verify no all-day events
        resp = client.get(f"/feed/{token}/weather.ics")
        assert resp.status_code == 200
        vevents = _parse_vevents(resp.content)
        allday = [e for e in vevents if not hasattr(e["DTSTART"].dt, "hour")]
        assert len(allday) == 0
