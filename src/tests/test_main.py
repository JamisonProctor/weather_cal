from src.app import main
from src.models.forecast import Forecast


def test_get_schedule_time_defaults(monkeypatch):
    monkeypatch.delenv("SCHEDULE_TIME", raising=False)

    assert main.get_schedule_time() == "00:23"


def test_get_schedule_time_uses_env(monkeypatch):
    monkeypatch.setenv("SCHEDULE_TIME", "00:17")

    assert main.get_schedule_time() == "00:17"


def test_get_schedule_time_rejects_invalid(monkeypatch):
    monkeypatch.setenv("SCHEDULE_TIME", "not-a-time")

    assert main.get_schedule_time() == "00:23"


def test_main_runs_full_pipeline(monkeypatch):
    raw_forecasts = {
        "Munich, Germany": [
            Forecast(
                date="2099-01-01",
                location="Munich, Germany",
                high=20,
                low=10,
                times=["2099-01-01T12:00"],
                temps=[20],
                codes=[1],
                rain=[0],
                winds=[5],
            )
        ],
        "Berlin, Germany": [
            Forecast(
                date="2099-01-02",
                location="Berlin, Germany",
                high=15,
                low=7,
                times=["2099-01-02T12:00"],
                temps=[15],
                codes=[2],
                rain=[10],
                winds=[4],
            )
        ],
    }
    saved_forecasts = []
    updated_forecasts = []

    class FakeStore:
        def upsert_forecast(self, forecast):
            saved_forecasts.append(forecast)

        def get_forecasts_future(self, days):
            assert days == 14
            return list(saved_forecasts)

    synced_warnings = []

    class FakeCalendarService:
        def upsert_event(self, forecast):
            updated_forecasts.append(forecast)

        def sync_warning_events(self, date, location, windows, timezone):
            synced_warnings.append((date, location, windows))

    monkeypatch.setenv("ENABLE_GOOGLE_CALENDAR_SYNC", "true")
    monkeypatch.setattr(main, "get_locations", lambda: ["Munich, Germany", "Berlin, Germany"])
    monkeypatch.setattr(main, "ForecastStore", FakeStore)
    monkeypatch.setattr(
        main.ForecastService,
        "fetch_forecasts",
        lambda location, forecast_days: raw_forecasts[location],
    )
    monkeypatch.setattr(main, "format_summary", lambda forecast: f"summary-{forecast.location}")
    monkeypatch.setattr(main, "format_detailed_forecast", lambda forecast: f"description-{forecast.location}")
    monkeypatch.setattr(main, "get_warning_windows", lambda forecast: [])
    monkeypatch.setattr(main, "CalendarService", FakeCalendarService)

    main.main()

    assert len(saved_forecasts) == 2
    assert len(updated_forecasts) == 2
    assert [forecast.location for forecast in saved_forecasts] == ["Munich, Germany", "Berlin, Germany"]
    assert all(forecast.summary.startswith("summary-") for forecast in saved_forecasts)
    assert all(forecast.description.startswith("description-") for forecast in saved_forecasts)
    assert updated_forecasts == saved_forecasts
    assert len(synced_warnings) == 2


def test_main_does_not_update_calendar_when_fetch_fails(monkeypatch):
    store_calls = {"created": 0, "get_future": 0, "upsert": 0}
    calendar_calls = {"created": 0}

    class FakeStore:
        def __init__(self):
            store_calls["created"] += 1

        def upsert_forecast(self, forecast):
            store_calls["upsert"] += 1

        def get_forecasts_future(self, days):
            store_calls["get_future"] += 1
            return []

    class FakeCalendarService:
        def __init__(self):
            calendar_calls["created"] += 1

    def fail_fetch(location, forecast_days):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setenv("ENABLE_GOOGLE_CALENDAR_SYNC", "true")
    monkeypatch.setattr(main, "get_locations", lambda: ["Munich, Germany"])
    monkeypatch.setattr(main, "ForecastStore", FakeStore)
    monkeypatch.setattr(main.ForecastService, "fetch_forecasts", fail_fetch)
    monkeypatch.setattr(main, "CalendarService", FakeCalendarService)

    main.main()

    assert store_calls["created"] == 1
    assert store_calls["upsert"] == 0
    assert store_calls["get_future"] == 0
    assert calendar_calls["created"] == 1  # CalendarService is now initialised before the fetch loop
