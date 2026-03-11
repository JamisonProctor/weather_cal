import pytest
import requests

from src.services.forecast_service import ForecastService
from src.models.forecast import Forecast

# 1. Mock API responses

class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code
    def json(self):
        return self._json
    def raise_for_status(self):
        if self.status_code != 200:
            raise Exception("API Error")

# 2. Test get_coordinates_with_timezone success
def test_get_coordinates_success(monkeypatch):
    fake_geo = {
        "results": [{
            "latitude": 48.13,
            "longitude": 11.58,
            "timezone": "Europe/Berlin"
        }]
    }
    def mock_get(*args, **kwargs):
        return MockResponse(fake_geo)
    monkeypatch.setattr("requests.get", mock_get)
    lat, lon, tz = ForecastService.get_coordinates_with_timezone("Munich")
    assert lat == 48.13
    assert lon == 11.58
    assert tz == "Europe/Berlin"

# 3. Test get_coordinates_with_timezone not found
def test_get_coordinates_not_found(monkeypatch):
    fake_geo = {"results": []}
    def mock_get(*args, **kwargs):
        return MockResponse(fake_geo)
    monkeypatch.setattr("requests.get", mock_get)
    with pytest.raises(ValueError):
        ForecastService.get_coordinates_with_timezone("Atlantis")

# 4. Test fetch_forecasts returns Forecast objects
def test_fetch_forecasts(monkeypatch):
    fake_forecast = {
        "hourly": {
            "time": [
                "2025-08-02T06:00", "2025-08-02T07:00", "2025-08-02T08:00",
                "2025-08-02T12:00", "2025-08-02T13:00", "2025-08-02T14:00"
            ],
            "temperature_2m": [15, 16, 17, 22, 23, 24],
            "weathercode": [1, 1, 1, 2, 2, 2],
            "precipitation_probability": [0, 10, 20, 10, 0, 0],
            "precipitation": [0, 0, 0.1, 0, 0, 0],
            "windspeed_10m": [5, 6, 7, 8, 7, 6]
        }
    }
    # mock requests.get for coordinates
    monkeypatch.setattr(ForecastService, "get_coordinates_with_timezone", lambda *a, **k: (48.13, 11.58, "Europe/Berlin"))
    # mock requests.get for forecast
    def mock_get(*args, **kwargs):
        return MockResponse(fake_forecast)
    monkeypatch.setattr("requests.get", mock_get)
    forecasts = ForecastService.fetch_forecasts("Munich")
    assert isinstance(forecasts, list)
    assert len(forecasts) == 1
    forecast = forecasts[0]
    assert isinstance(forecast, Forecast)
    assert forecast.date == "2025-08-02"
    assert forecast.high == 24
    assert forecast.low == 15
    assert len(forecast.temps) == 6

# 5. Test fetch_forecasts handles empty data
def test_fetch_forecasts_empty(monkeypatch):
    empty_data = {"hourly": {"time": [], "temperature_2m": [], "weathercode": [], "precipitation_probability": [], "precipitation": [], "windspeed_10m": []}}
    monkeypatch.setattr(ForecastService, "get_coordinates_with_timezone", lambda *a, **k: (48.13, 11.58, "Europe/Berlin"))
    monkeypatch.setattr("requests.get", lambda *a, **k: MockResponse(empty_data))
    forecasts = ForecastService.fetch_forecasts("Munich")
    assert isinstance(forecasts, list)
    assert len(forecasts) == 0

# 6. Test fetch_forecasts error handling (API fails)
def test_fetch_forecasts_api_fail(monkeypatch):
    monkeypatch.setattr(ForecastService, "get_coordinates_with_timezone", lambda *a, **k: (48.13, 11.58, "Europe/Berlin"))
    def mock_get(*a, **k):
        raise Exception("API totally broken")
    monkeypatch.setattr("requests.get", mock_get)
    with pytest.raises(Exception):
        ForecastService.fetch_forecasts("Munich")


# 7. Test get_coordinates_with_timezone with different language param
def test_get_coordinates_with_different_language(monkeypatch):
    fake_geo = {
        "results": [{
            "latitude": 40.41,
            "longitude": -3.7,
            "timezone": "Europe/Madrid"
        }]
    }
    def mock_get(*args, **kwargs):
        assert kwargs['params']['language'] == "es"
        return MockResponse(fake_geo)
    monkeypatch.setattr("requests.get", mock_get)
    lat, lon, tz = ForecastService.get_coordinates_with_timezone("Madrid", language="es")
    assert lat == 40.41 and lon == -3.7 and tz == "Europe/Madrid"

# 8. Test fetch_forecasts with custom lat/lon (should not call geocode)
def test_fetch_forecasts_with_lat_lon(monkeypatch):
    fake_forecast = {
        "hourly": {
            "time": ["2025-08-03T12:00"],
            "temperature_2m": [30],
            "weathercode": [1],
            "precipitation_probability": [0],
            "windspeed_10m": [5]
        }
    }
    monkeypatch.setattr("requests.get", lambda *a, **k: MockResponse(fake_forecast))
    forecasts = ForecastService.fetch_forecasts(
        location="Custom", lat=52.5, lon=13.4, forecast_days=1
    )
    assert len(forecasts) == 1
    assert forecasts[0].high == 30

# 9. Test varying forecast_days parameter
def test_forecast_days(monkeypatch):
    fake_data = {
        "hourly": {
            "time": [f"2025-08-{day:02d}T12:00" for day in range(1, 4)],
            "temperature_2m": [10, 20, 30],
            "weathercode": [1, 2, 3],
            "precipitation_probability": [0, 10, 20],
            "windspeed_10m": [3, 4, 5],
        }
    }
    monkeypatch.setattr(ForecastService, "get_coordinates_with_timezone", lambda *a, **k: (1.0, 2.0, "UTC"))
    monkeypatch.setattr("requests.get", lambda *a, **k: MockResponse(fake_data))
    forecasts = ForecastService.fetch_forecasts("Anywhere", forecast_days=3)
    assert len(forecasts) == 3
    assert [f.high for f in forecasts] == [10, 20, 30]

# 10. Test start_hour/end_hour boundaries
def test_fetch_forecasts_time_boundaries(monkeypatch):
    # Only 5am and 11pm data, should be filtered out with default boundaries
    fake_data = {
        "hourly": {
            "time": ["2025-08-02T05:00", "2025-08-02T23:00"],
            "temperature_2m": [5, 23],
            "weathercode": [1, 2],
            "precipitation_probability": [0, 0],
            "windspeed_10m": [1, 2],
        }
    }
    monkeypatch.setattr(ForecastService, "get_coordinates_with_timezone", lambda *a, **k: (1.0, 2.0, "UTC"))
    monkeypatch.setattr("requests.get", lambda *a, **k: MockResponse(fake_data))
    forecasts = ForecastService.fetch_forecasts("Filtered", start_hour=6, end_hour=22)
    assert len(forecasts) == 0  # Should filter out all

    # Should include if start/end are wider
    forecasts = ForecastService.fetch_forecasts("Filtered", start_hour=5, end_hour=23)
    assert len(forecasts) == 1
    assert forecasts[0].high == 23 and forecasts[0].low == 5

# 11. Test Forecast dataclass creation and defaults
def test_forecast_dataclass():
    forecast = Forecast(
        date="2025-08-04",
        location="Munich",
        high=21,
        low=12,
        summary="Test summary",
        times=["2025-08-04T12:00"],
        temps=[21],
        codes=[1],
        rain=[0],
        winds=[5],
        description="Some description"
    )
    assert forecast.date == "2025-08-04"
    assert forecast.location == "Munich"
    assert forecast.high == 21
    assert forecast.low == 12
    assert forecast.summary == "Test summary"
    assert forecast.times == ["2025-08-04T12:00"]
    assert forecast.temps == [21]
    assert forecast.codes == [1]
    assert forecast.rain == [0]
    assert forecast.winds == [5]
    assert forecast.description == "Some description"

# 12. Test fetch_forecasts with missing keys in API response
def test_fetch_forecasts_missing_keys(monkeypatch):
    # Missing windspeed_10m
    fake_data = {
        "hourly": {
            "time": ["2025-08-03T12:00"],
            "temperature_2m": [25],
            "weathercode": [2],
            "precipitation_probability": [15]
            # windspeed_10m missing
        }
    }
    monkeypatch.setattr(ForecastService, "get_coordinates_with_timezone", lambda *a, **k: (0.0, 0.0, "UTC"))
    monkeypatch.setattr("requests.get", lambda *a, **k: MockResponse(fake_data))
    forecasts = ForecastService.fetch_forecasts("NoWind")
    assert len(forecasts) == 1
    assert forecasts[0].winds == [0]  # Should default to 0

# 13. Test fetch_forecasts with partial/empty inputs
def test_fetch_forecasts_partial(monkeypatch):
    fake_data = {
        "hourly": {
            "time": ["2025-08-03T12:00"],
            "temperature_2m": [],
            "weathercode": [2],
            "precipitation_probability": [],
            "windspeed_10m": [],
        }
    }
    monkeypatch.setattr(ForecastService, "get_coordinates_with_timezone", lambda *a, **k: (0.0, 0.0, "UTC"))
    monkeypatch.setattr("requests.get", lambda *a, **k: MockResponse(fake_data))
    forecasts = ForecastService.fetch_forecasts("PartialData")
    # Should not crash, and produce a Forecast object with partial data
    assert len(forecasts) == 1
    assert forecasts[0].temps == [None]
    assert forecasts[0].rain == [None]
    assert forecasts[0].winds == [None]


def test_request_json_retries_timeout_then_succeeds(monkeypatch):
    calls = {"count": 0}

    def mock_get(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise requests.exceptions.ReadTimeout("slow")
        return MockResponse({"ok": True})

    sleep_calls = []

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("src.services.forecast_service.time.sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(ForecastService, "MAX_ATTEMPTS", 3)
    monkeypatch.setattr(ForecastService, "RETRY_BACKOFF_SECONDS", (1, 2))

    data = ForecastService._request_json_with_retry(
        "https://example.com",
        params={"a": 1},
        context="test request",
    )

    assert data == {"ok": True}
    assert calls["count"] == 3
    assert sleep_calls == [1, 2]


def test_request_json_retries_connection_error(monkeypatch):
    calls = {"count": 0}

    def mock_get(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise requests.exceptions.ConnectionError("refused")
        return MockResponse({"ok": True})

    sleep_calls = []
    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("src.services.forecast_service.time.sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr(ForecastService, "MAX_ATTEMPTS", 3)
    monkeypatch.setattr(ForecastService, "RETRY_BACKOFF_SECONDS", (1, 2))

    data = ForecastService._request_json_with_retry(
        "https://example.com", params={}, context="conn test",
    )
    assert data == {"ok": True}
    assert calls["count"] == 3
    assert len(sleep_calls) == 2


def test_request_json_retries_server_error_502(monkeypatch):
    calls = {"count": 0}

    def mock_get(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 2:
            error = requests.exceptions.HTTPError("502")
            resp = type("R", (), {"status_code": 502})()
            error.response = resp
            raise error
        return MockResponse({"ok": True})

    sleep_calls = []
    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("src.services.forecast_service.time.sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr(ForecastService, "MAX_ATTEMPTS", 3)
    monkeypatch.setattr(ForecastService, "RETRY_BACKOFF_SECONDS", (1, 2))

    data = ForecastService._request_json_with_retry(
        "https://example.com", params={}, context="502 test",
    )
    assert data == {"ok": True}
    assert calls["count"] == 2


def test_is_retryable_http_error_missing_response():
    error = requests.exceptions.HTTPError("no response")
    error.response = None
    assert ForecastService._is_retryable_http_error(error) is False


def test_get_coordinates_missing_timezone_defaults(monkeypatch):
    fake_geo = {
        "results": [{
            "latitude": 48.13,
            "longitude": 11.58,
            # no "timezone" key
        }]
    }
    monkeypatch.setattr("requests.get", lambda *a, **k: MockResponse(fake_geo))
    lat, lon, tz = ForecastService.get_coordinates_with_timezone("Munich")
    assert lat == 48.13
    assert lon == 11.58
    assert tz == "Europe/Berlin"  # default fallback


def test_request_json_does_not_retry_client_error(monkeypatch):
    class ErrorResponse:
        status_code = 400

    def mock_get(*args, **kwargs):
        response = MockResponse({}, status_code=200)
        error = requests.exceptions.HTTPError("bad request")
        error.response = ErrorResponse()
        raise error

    sleep_calls = []

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("src.services.forecast_service.time.sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(ForecastService, "MAX_ATTEMPTS", 3)

    with pytest.raises(requests.exceptions.HTTPError):
        ForecastService._request_json_with_retry(
            "https://example.com",
            params={"a": 1},
            context="test request",
        )

    assert sleep_calls == []
