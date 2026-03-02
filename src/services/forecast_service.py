import os
import logging
import time

from typing import List
from datetime import datetime
from dotenv import load_dotenv
import requests

from src.utils.logging_config import setup_logging
from src.models.forecast import Forecast

setup_logging()
logger = logging.getLogger(__name__)

load_dotenv()

class ForecastService:
    OPEN_METEO_URL = os.getenv("OPEN_METEO_URL")
    GEOCODE_URL = os.getenv("GEOCODE_URL")
    CONNECT_TIMEOUT = float(os.getenv("WEATHER_API_CONNECT_TIMEOUT", "10"))
    READ_TIMEOUT = float(os.getenv("WEATHER_API_READ_TIMEOUT", "60"))
    MAX_ATTEMPTS = max(1, int(os.getenv("WEATHER_API_MAX_ATTEMPTS", "3")))
    RETRY_BACKOFF_SECONDS = (
        int(os.getenv("WEATHER_API_RETRY_DELAY_FIRST", "15")),
        int(os.getenv("WEATHER_API_RETRY_DELAY_SECOND", "45")),
    )

    @classmethod
    def _get_request_timeout(cls) -> tuple[float, float]:
        return cls.CONNECT_TIMEOUT, cls.READ_TIMEOUT

    @classmethod
    def _is_retryable_http_error(cls, exc: requests.exceptions.HTTPError) -> bool:
        response = getattr(exc, "response", None)
        if response is None or response.status_code is None:
            return False
        return 500 <= response.status_code < 600

    @classmethod
    def _request_json_with_retry(cls, url: str, *, params: dict, context: str) -> dict:
        timeout = cls._get_request_timeout()
        last_exc = None

        for attempt in range(1, cls.MAX_ATTEMPTS + 1):
            try:
                response = requests.get(url, params=params, timeout=timeout)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError as exc:
                last_exc = exc
                retryable = cls._is_retryable_http_error(exc)
                error_summary = f"HTTP {exc.response.status_code}" if getattr(exc, "response", None) else str(exc)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_exc = exc
                retryable = True
                error_summary = exc.__class__.__name__
            except requests.exceptions.RequestException as exc:
                last_exc = exc
                retryable = False
                error_summary = exc.__class__.__name__
            if attempt >= cls.MAX_ATTEMPTS or not retryable:
                logger.error(
                    "Request failed for %s on attempt %s/%s: %s",
                    context,
                    attempt,
                    cls.MAX_ATTEMPTS,
                    error_summary,
                    exc_info=True,
                )
                raise last_exc

            backoff_index = min(attempt - 1, len(cls.RETRY_BACKOFF_SECONDS) - 1)
            delay = cls.RETRY_BACKOFF_SECONDS[backoff_index]
            logger.warning(
                "Transient request failure for %s on attempt %s/%s: %s. Retrying in %ss.",
                context,
                attempt,
                cls.MAX_ATTEMPTS,
                error_summary,
                delay,
            )
            time.sleep(delay)

        if last_exc is not None:
            raise last_exc

    @classmethod
    def get_coordinates_with_timezone(cls, location_name: str, language: str = "en"):
        try:
            logger.info(f"Fetching coordinates for location: '{location_name}' (lang={language})")
            params = {
                "name": location_name,
                "count": 1,
                "language": language,
                "format": "json"
            }
            data = cls._request_json_with_retry(
                cls.GEOCODE_URL,
                params=params,
                context=f"geocoding '{location_name}'",
            )
            if "results" not in data or not data["results"]:
                logger.error(f"Location '{location_name}' not found in geocode API response")
                raise ValueError(f"Location '{location_name}' not found")
            result = data["results"][0]
            lat = result["latitude"]
            lon = result["longitude"]
            tz = result.get("timezone", "Europe/Berlin")
            logger.info(f"Coordinates for '{location_name}': ({lat}, {lon}), timezone: {tz}")
            return lat, lon, tz
        except Exception:
            logger.exception(f"Error fetching coordinates for location '{location_name}'")
            raise

    @classmethod
    def fetch_forecasts(
        cls,
        location: str,
        forecast_days: int = 7,
        timezone: str = None,
        language: str = "en",
        lat: float = None,
        lon: float = None,
        start_hour: int = 6, 
        end_hour: int = 22,
    ) -> List[Forecast]:
        logger.info(f"Fetching forecasts for location={location}, forecast_days={forecast_days}, timezone={timezone}, language={language}, lat={lat}, lon={lon}, start_hour={start_hour}, end_hour={end_hour}")
        if lat is None or lon is None:
            # Look up lat/lon/tz from location
            lat, lon, tz = cls.get_coordinates_with_timezone(location, language)
            tz = timezone or tz or "Europe/Berlin"
        else:
            tz = timezone or "Europe/Berlin"
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "temperature_2m,weathercode,precipitation_probability,windspeed_10m",
            "timezone": tz,
            "forecast_days": forecast_days,
        }
        try:
            data = cls._request_json_with_retry(
                cls.OPEN_METEO_URL,
                params=params,
                context=f"forecast lat={lat}, lon={lon}",
            )
            logger.debug(f"Raw forecast data: {data}")
        except Exception:
            logger.error(f"Error fetching forecast data for lat={lat}, lon={lon}")
            raise

        times = data["hourly"]["time"]
        temps = data["hourly"]["temperature_2m"]
        codes = data["hourly"]["weathercode"]
        rain_probs = data["hourly"].get("precipitation_probability", [0]*len(times))
        winds = data["hourly"].get("windspeed_10m", [0]*len(times))

        daily_data = {}
        for idx, t in enumerate(times):
            dt = datetime.fromisoformat(t)
            date_str = dt.date().isoformat()
            if start_hour <= dt.hour <= end_hour:
                if date_str not in daily_data:
                    daily_data[date_str] = {"times": [], "temps": [], "codes": [], "rain": [], "winds": []}
                daily_data[date_str]["times"].append(t)
                daily_data[date_str]["temps"].append(temps[idx] if idx < len(temps) else None)
                daily_data[date_str]["codes"].append(codes[idx] if idx < len(codes) else None)
                daily_data[date_str]["rain"].append(rain_probs[idx] if idx < len(rain_probs) else None)
                daily_data[date_str]["winds"].append(winds[idx] if idx < len(winds) else None)

        forecasts = []
        for date, vals in daily_data.items():
            high = max(vals["temps"])
            low = min(vals["temps"])
            forecasts.append(Forecast(
                date=date,
                location=location,
                high=high,
                low=low,
                summary="",
                times=vals["times"],
                temps=vals["temps"],
                codes=vals["codes"],
                rain=vals["rain"],
                winds=vals["winds"],
                description=None
            ))
            logger.info(f"Created forecast for {date}: high={high}, low={low}")
        return forecasts
