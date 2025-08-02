# forecast_service.py

import os
import requests
import logging

from typing import List
from datetime import datetime
from dotenv import load_dotenv
from utils.logging_config import setup_logging
from forecast import Forecast

setup_logging()
logger = logging.getLogger(__name__)

load_dotenv()

class ForecastService:
    OPEN_METEO_URL = os.getenv("OPEN_METEO_URL")
    GEOCODE_URL = os.getenv("GEOCODE_URL")
    DEFAULT_LOCATION = os.getenv("DEFAULT_LOCATION", "Munich, Germany")

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
            resp = requests.get(cls.GEOCODE_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
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
        location: str = None,
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
            response = requests.get(cls.OPEN_METEO_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            logger.debug(f"Raw forecast data: {data}")
        except Exception:
            logger.error(f"Error fetching forecast data for lat={lat}, lon={lon}")
            logger.exception("Exception details:")
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
                details=None
            ))
            logger.info(f"Created forecast for {date}: high={high}, low={low}")
        return forecasts