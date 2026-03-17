from datetime import date, timedelta

import schedule

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
        "Munich": [
            Forecast(
                date="2099-01-01",
                location="Munich",
                high=20,
                low=10,
                times=["2099-01-01T12:00"],
                temps=[20],
                codes=[1],
                rain=[0],
                winds=[5],
            )
        ],
        "Berlin": [
            Forecast(
                date="2099-01-02",
                location="Berlin",
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

    class FakeStore:
        def upsert_forecast(self, forecast):
            saved_forecasts.append(forecast)

    monkeypatch.setattr(main, "get_locations", lambda: [
        {"location": "Munich", "lat": 48.137, "lon": 11.576, "timezone": "Europe/Berlin"},
        {"location": "Berlin", "lat": 52.520, "lon": 13.405, "timezone": "Europe/Berlin"},
    ])
    monkeypatch.setattr(main, "ForecastStore", FakeStore)
    monkeypatch.setattr(
        main.ForecastService,
        "fetch_forecasts",
        lambda location, forecast_days, **kwargs: raw_forecasts[location],
    )
    monkeypatch.setattr(main, "format_summary", lambda forecast: f"summary-{forecast.location}")
    monkeypatch.setattr(main, "format_detailed_forecast", lambda forecast: f"description-{forecast.location}")
    monkeypatch.setattr(main, "_push_google_calendars", lambda: None)

    main.main()

    assert len(saved_forecasts) == 2
    assert [forecast.location for forecast in saved_forecasts] == ["Munich", "Berlin"]
    assert all(forecast.summary.startswith("summary-") for forecast in saved_forecasts)
    assert all(forecast.description.startswith("description-") for forecast in saved_forecasts)


def test_short_term_main_fetches_and_stores(monkeypatch):
    raw_forecasts = {
        "Munich": [
            Forecast(
                date="2099-01-01",
                location="Munich",
                high=20,
                low=10,
                times=["2099-01-01T12:00"],
                temps=[20],
                codes=[1],
                rain=[0],
                winds=[5],
            )
        ],
        "Berlin": [
            Forecast(
                date="2099-01-01",
                location="Berlin",
                high=18,
                low=8,
                times=["2099-01-01T12:00"],
                temps=[18],
                codes=[2],
                rain=[5],
                winds=[3],
            )
        ],
    }
    saved_forecasts = []

    class FakeStore:
        def upsert_forecast(self, forecast):
            saved_forecasts.append(forecast)

    monkeypatch.setattr(main, "get_locations", lambda: [
        {"location": "Munich", "lat": 48.137, "lon": 11.576, "timezone": "Europe/Berlin"},
        {"location": "Berlin", "lat": 52.520, "lon": 13.405, "timezone": "Europe/Berlin"},
    ])
    monkeypatch.setattr(main, "ForecastStore", FakeStore)
    monkeypatch.setattr(
        main.ForecastService,
        "fetch_forecasts",
        lambda location, forecast_days, **kwargs: raw_forecasts[location],
    )
    monkeypatch.setattr(main, "format_summary", lambda forecast: f"summary-{forecast.location}")
    monkeypatch.setattr(main, "format_detailed_forecast", lambda forecast: f"desc-{forecast.location}")

    main.short_term_main()

    assert len(saved_forecasts) == 2
    assert all(f.summary.startswith("summary-") for f in saved_forecasts)
    assert all(f.description.startswith("desc-") for f in saved_forecasts)


def test_short_term_main_continues_on_error(monkeypatch):
    """A fetch failure for one location should not abort the others."""
    good_forecast = Forecast(
        date="2099-01-01",
        location="Berlin",
        high=15,
        low=5,
        times=["2099-01-01T12:00"],
        temps=[15],
        codes=[1],
        rain=[0],
        winds=[2],
    )
    saved_forecasts = []

    class FakeStore:
        def upsert_forecast(self, forecast):
            saved_forecasts.append(forecast)

    def fake_fetch(location, forecast_days, **kwargs):
        if location == "Munich":
            raise RuntimeError("fetch failed")
        return [good_forecast]

    monkeypatch.setattr(main, "get_locations", lambda: [
        {"location": "Munich", "lat": 48.137, "lon": 11.576, "timezone": "Europe/Berlin"},
        {"location": "Berlin", "lat": 52.520, "lon": 13.405, "timezone": "Europe/Berlin"},
    ])
    monkeypatch.setattr(main, "ForecastStore", FakeStore)
    monkeypatch.setattr(main.ForecastService, "fetch_forecasts", fake_fetch)
    monkeypatch.setattr(main, "format_summary", lambda f: "")
    monkeypatch.setattr(main, "format_detailed_forecast", lambda f: "")

    main.short_term_main()  # should not raise

    assert len(saved_forecasts) == 1
    assert saved_forecasts[0].location == "Berlin"


def test_main_does_not_store_when_fetch_fails(monkeypatch):
    store_calls = {"created": 0, "upsert": 0}
    push_calls = {"count": 0}

    class FakeStore:
        def __init__(self):
            store_calls["created"] += 1

        def upsert_forecast(self, forecast):
            store_calls["upsert"] += 1

    def fail_fetch(location, forecast_days, **kwargs):
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(main, "get_locations", lambda: [
        {"location": "Munich", "lat": 48.137, "lon": 11.576, "timezone": "Europe/Berlin"},
    ])
    monkeypatch.setattr(main, "ForecastStore", FakeStore)
    monkeypatch.setattr(main.ForecastService, "fetch_forecasts", fail_fetch)
    monkeypatch.setattr(main, "_push_google_calendars", lambda: push_calls.update(count=push_calls["count"] + 1))

    main.main()

    assert store_calls["created"] == 1
    assert store_calls["upsert"] == 0
    assert push_calls["count"] == 1  # Google push still runs (handles errors internally)


# --- _process_and_store tests ---

def test_process_and_store_formats_and_upserts(monkeypatch):
    forecasts = [
        Forecast(date="2099-01-01", location="Munich", high=20, low=10,
                 times=["2099-01-01T12:00"], temps=[20], codes=[1], rain=[0], winds=[5]),
    ]
    saved = []

    class FakeStore:
        def upsert_forecast(self, f):
            saved.append(f)

    monkeypatch.setattr(main, "format_summary", lambda f, prefs=None: "sum")
    monkeypatch.setattr(main, "format_detailed_forecast", lambda f, prefs=None: "desc")

    main._process_and_store(forecasts, FakeStore())

    assert len(saved) == 1
    assert saved[0].summary == "sum"
    assert saved[0].description == "desc"


# --- refresh_tier tests ---

def _setup_tier_test(monkeypatch, expected_forecast_days=None, expected_start_date=None, expected_end_date=None):
    """Helper to set up mocking for tier refresh tests."""
    batch_calls = []

    def fake_batch(locations, forecast_days=None, start_date=None, end_date=None, **kw):
        batch_calls.append({
            "locations": locations,
            "forecast_days": forecast_days,
            "start_date": start_date,
            "end_date": end_date,
        })
        result = {}
        for loc in locations:
            result[loc["location"]] = [
                Forecast(date="2099-01-01", location=loc["location"], high=20, low=10,
                         times=["2099-01-01T12:00"], temps=[20], codes=[1], rain=[0], winds=[5])
            ]
        return result

    class FakeStore:
        def upsert_forecast(self, f):
            pass

    monkeypatch.setattr(main.ForecastService, "fetch_forecasts_batch", fake_batch)
    monkeypatch.setattr(main, "ForecastStore", FakeStore)
    monkeypatch.setattr(main, "format_summary", lambda f, prefs=None: "")
    monkeypatch.setattr(main, "format_detailed_forecast", lambda f, prefs=None: "")
    monkeypatch.setattr(main, "_push_google_calendars", lambda **kw: None)

    return batch_calls


def test_refresh_tier1_calls_batch_with_2_days(monkeypatch):
    batch_calls = _setup_tier_test(monkeypatch)
    locations = [
        {"location": "Munich", "lat": 48.13, "lon": 11.58, "timezone": "Europe/Berlin"},
    ]
    main.refresh_tier1(locations)

    assert len(batch_calls) == 1
    assert batch_calls[0]["forecast_days"] == 2
    assert batch_calls[0]["start_date"] is None


def test_refresh_tier2_calls_batch_with_date_range(monkeypatch):
    batch_calls = _setup_tier_test(monkeypatch)
    locations = [
        {"location": "Munich", "lat": 48.13, "lon": 11.58, "timezone": "Europe/Berlin"},
    ]
    main.refresh_tier2(locations)

    assert len(batch_calls) == 1
    today = date.today()
    assert batch_calls[0]["start_date"] == (today + timedelta(days=2)).isoformat()
    assert batch_calls[0]["end_date"] == (today + timedelta(days=4)).isoformat()


def test_refresh_tier3_calls_batch_with_date_range(monkeypatch):
    batch_calls = _setup_tier_test(monkeypatch)
    locations = [
        {"location": "Munich", "lat": 48.13, "lon": 11.58, "timezone": "Europe/Berlin"},
    ]
    main.refresh_tier3(locations)

    assert len(batch_calls) == 1
    today = date.today()
    assert batch_calls[0]["start_date"] == (today + timedelta(days=5)).isoformat()
    assert batch_calls[0]["end_date"] == (today + timedelta(days=14)).isoformat()


def test_refresh_tier_empty_locations(monkeypatch):
    """Tier functions should no-op with empty locations."""
    batch_calls = _setup_tier_test(monkeypatch)
    main.refresh_tier1([])
    main.refresh_tier2([])
    main.refresh_tier3([])
    assert len(batch_calls) == 0


# --- _schedule_tier_jobs tests ---

def test_schedule_tier_jobs_creates_correct_job_count(monkeypatch):
    monkeypatch.setattr(main, "_get_tier_times", lambda: (
        ["05:30", "11:00", "15:30", "18:30", "22:00"],
        ["06:00", "17:00"],
        ["02:00"],
    ))
    schedule.clear()

    tz_groups = {
        1: [{"location": "Munich", "lat": 48.13, "lon": 11.58, "timezone": "Europe/Berlin"}],
        9: [{"location": "Tokyo", "lat": 35.68, "lon": 139.69, "timezone": "Asia/Tokyo"}],
    }
    main._schedule_tier_jobs(tz_groups)

    jobs = schedule.get_jobs()
    # Per group: 5 tier1 + 2 tier2 + 1 tier3 = 8 jobs, x2 groups = 16
    assert len(jobs) == 16

    schedule.clear()


def test_reschedule_clears_and_recreates(monkeypatch):
    monkeypatch.setattr(main, "_get_tier_times", lambda: (["12:00"], ["12:00"], ["12:00"]))
    monkeypatch.setattr(main, "group_locations_by_tz_offset", lambda: {
        0: [{"location": "London", "lat": 51.5, "lon": -0.12, "timezone": "Europe/London"}],
    })
    schedule.clear()

    # Create initial jobs
    main._schedule_tier_jobs({
        0: [{"location": "London", "lat": 51.5, "lon": -0.12, "timezone": "Europe/London"}],
    })
    initial_count = len(schedule.get_jobs())
    assert initial_count == 3  # 1 + 1 + 1

    # Reschedule should clear and recreate
    main.reschedule()
    assert len(schedule.get_jobs()) == 3

    schedule.clear()


def test_get_tier_times_from_env(monkeypatch):
    monkeypatch.setenv("TIER1_TIMES", "06:00,12:00")
    monkeypatch.setenv("TIER2_TIMES", "07:00")
    monkeypatch.setenv("TIER3_TIME", "03:00")
    t1, t2, t3 = main._get_tier_times()
    assert t1 == ["06:00", "12:00"]
    assert t2 == ["07:00"]
    assert t3 == ["03:00"]


def test_get_tier_times_defaults(monkeypatch):
    monkeypatch.delenv("TIER1_TIMES", raising=False)
    monkeypatch.delenv("TIER2_TIMES", raising=False)
    monkeypatch.delenv("TIER3_TIME", raising=False)
    t1, t2, t3 = main._get_tier_times()
    assert len(t1) == 5
    assert len(t2) == 2
    assert len(t3) == 1
