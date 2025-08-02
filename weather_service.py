import requests
import os
import logging

from datetime import datetime
from statistics import mean
from collections import Counter
from dotenv import load_dotenv

load_dotenv()

OPEN_METEO_URL = os.getenv("OPEN_METEO_URL")
GEOCODE_URL = os.getenv("GEOCODE_URL")
DEFAULT_LOCATION = os.getenv("DEFAULT_LOCATION", "Munich, Germany")

def get_coordinates(location_name: str):
    """Fetch lat/lon from Open Meteo's geocoding API."""
    params = {
        "name": location_name,
        "count": 1,
        "language": "en",
        "format": "json"
    }
    resp = requests.get(GEOCODE_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if "results" not in data or not data["results"]:
        raise ValueError(f"Location '{location_name}' not found")

    result = data["results"][0]
    return result["latitude"], result["longitude"]

def map_code_to_emoji(code: int) -> str:
    """
    Maps Open Meteo weather codes to emoji summary.
    Ref: https://open-meteo.com/en/docs
    """
    mapping = {
        0: "☀️",   # Clear
        1: "🌤️",  # Mainly clear
        2: "⛅",   # Partly cloudy
        3: "☁️",   # Overcast
        45: "🌫️", # Fog
        48: "🌫️",
        51: "🌦️", # Light drizzle
        61: "🌧️", # Rain
        63: "🌧️",
        65: "🌧️",
        71: "❄️", # Snow
        80: "🌦️",
        95: "⛈️", # Thunderstorm
    }
    return mapping.get(code, "❓")

def map_morning_afternoon(times, temps, codes):
    morning = [(temp, code) for t, temp, code in zip(times, temps, codes) if 6 <= datetime.fromisoformat(t).hour < 12]
    afternoon = [(temp, code) for t, temp, code in zip(times, temps, codes) if 12 <= datetime.fromisoformat(t).hour <= 22]
    morning_temp = mean([x[0] for x in morning]) if morning else 0
    afternoon_temp = mean([x[0] for x in afternoon]) if afternoon else 0
    morning_emoji = map_code_to_emoji(Counter([x[1] for x in morning]).most_common(1)[0][0]) if morning else ""
    afternoon_emoji = map_code_to_emoji(Counter([x[1] for x in afternoon]).most_common(1)[0][0]) if afternoon else ""
    return morning_emoji, morning_temp, afternoon_emoji, afternoon_temp

def fetch_forecast(location: str = DEFAULT_LOCATION):
    """
    Fetches 7-day weather forecast for given location from Open Meteo.
    Returns a list of dicts: [{'date': 'YYYY-MM-DD', 'high': 23, 'low': 14, 'summary': 'L14H23☀️➡️☁️➡️🌧️'}, ...]
    Focuses on daytime weather between 06:00 and 22:00.
    """
    try:
        lat, lon = get_coordinates(location)
    except Exception as e:
        print(f"[WARN] Geocoding failed for '{location}': {e}")
        print("Falling back to Munich coordinates")
        lat, lon = 48.1351, 11.5820

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,weathercode,precipitation_probability,windspeed_10m",
        "timezone": "Europe/Berlin",
        "forecast_days": 7,
    }

    response = requests.get(OPEN_METEO_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    times = data["hourly"]["time"]
    temps = data["hourly"]["temperature_2m"]
    codes = data["hourly"]["weathercode"]
    rain_probs = data["hourly"].get("precipitation_probability", [0]*len(times))
    winds = data["hourly"].get("windspeed_10m", [0]*len(times))

    daily_data = {}

    for t, temp, code in zip(times, temps, codes):
        dt = datetime.fromisoformat(t)
        date_str = dt.date().isoformat()

        # Users are primarily interested in daytime information
        # We only consider times between 06:00 and 22:00 for daily summaries
        if 6 <= dt.hour <= 22:
            if date_str not in daily_data:
                daily_data[date_str] = {
                    "temps": [],
                    "codes": [],
                    "times": [],
                    "rain": [],
                    "winds": []
                }
            daily_data[date_str]["temps"].append(temp)
            daily_data[date_str]["codes"].append(code)
            daily_data[date_str]["times"].append(t)
            daily_data[date_str]["rain"].append(rain_probs[times.index(t)])
            daily_data[date_str]["winds"].append(winds[times.index(t)])

    # Convert to list of clean forecasts
    forecasts = []
    for date, vals in daily_data.items():
        high = max(vals["temps"])
        low = min(vals["temps"])
        morning_emoji, morning_temp, afternoon_emoji, afternoon_temp = map_morning_afternoon(vals["times"], vals["temps"], vals["codes"])
        summary = f"AM{morning_emoji}{round(morning_temp)}° / PM{afternoon_emoji}{round(afternoon_temp)}°"

        forecasts.append({
            "date": date,
            "high": round(high),
            "low": round(low),
            "summary": summary,
            "times": vals["times"],
            "temps": vals["temps"],
            "codes": vals["codes"],
            "rain": vals["rain"],
            "winds": vals["winds"]
        })

    return forecasts

def fetch_forecasts_for_locations(locations: list[str]):
    """
    Fetch forecasts for a list of locations, avoiding duplicate API calls.
    Returns a dict mapping each location to its 7-day forecast list.
    """
    unique_locations = set(locations)
    results = {}
    for loc in unique_locations:
        try:
            results[loc] = fetch_forecast(loc)
        except Exception as e:
            print(f"[WARN] Could not fetch forecast for {loc}: {e}")
            results[loc] = []
    return results

logger = logging.getLogger(__name__)

# Add logging to key functions

_original_get_coordinates = get_coordinates
def get_coordinates(location_name: str):
    logger.info(f"Fetching coordinates for location: {location_name}")
    try:
        return _original_get_coordinates(location_name)
    except Exception as e:
        logger.error(f"Error fetching coordinates for {location_name}: {e}", exc_info=True)
        raise

_original_fetch_forecast = fetch_forecast
def fetch_forecast(location: str = DEFAULT_LOCATION):
    logger.info(f"Fetching 7-day weather forecast for location: {location}")
    try:
        return _original_fetch_forecast(location)
    except Exception as e:
        logger.error(f"Error fetching forecast for {location}: {e}", exc_info=True)
        raise

_original_fetch_forecasts_for_locations = fetch_forecasts_for_locations
def fetch_forecasts_for_locations(locations: list[str]):
    logger.info(f"Fetching forecasts for {len(locations)} locations: {locations}")
    try:
        return _original_fetch_forecasts_for_locations(locations)
    except Exception as e:
        logger.error("Error fetching forecasts for multiple locations", exc_info=True)
        raise

def format_detailed_forecast_hourly(times, temps, codes, rain_probs, winds, daily_high, daily_low):
    """
    Formats a detailed forecast string for calendar event description.
    Groups data into 3-hour blocks (06-08, 09-11, etc.) and displays:
    TIME EMOJI START°~MID°C 🌧️X% 💨Ykm/h
    """
    # Define target starting hours
    slots = [6, 9, 12, 15, 18, 21]
    description_lines = []
    data = list(zip(times, temps, codes, rain_probs, winds))

    for start in slots:
        block = [d for d in data if datetime.fromisoformat(d[0]).hour in (start, start+1, start+2)]
        if not block:
            continue

        start_temp = round(block[0][1])
        mid_temp = round(block[-1][1]) if len(block) > 1 else start_temp
        dominant_code = Counter([d[2] for d in block]).most_common(1)[0][0]
        emoji = map_code_to_emoji(dominant_code)
        rain = max([d[3] for d in block]) if any(d[3] is not None for d in block) else 0
        wind = round(max([d[4] for d in block])) if any(d[4] is not None for d in block) else 0

        line = f"{start:02d}:00 {emoji} {start_temp}°~{mid_temp}°C 🌧️{int(rain)}% 💨{wind}km/h"
        description_lines.append(line)

    description_lines.append(f"\nHigh: {daily_high}°C | Low: {daily_low}°C")
    return "\n".join(description_lines)

def parse_summary(summary: str):
    """
    Parses a forecast summary string in the format 'AM🌤️15° / PM🌧️22°'
    and returns (morning_emoji, morning_temp, afternoon_emoji, afternoon_temp).
    Falls back gracefully if format is unexpected.
    """
    try:
        if "AM" in summary and "PM" in summary:
            am_part = summary.split("AM")[1].split("/")[0].strip()
            pm_part = summary.split("PM")[1].strip()
            morning_emoji = ''.join([c for c in am_part if not c.isdigit() and c != '°'])
            morning_temp = ''.join(filter(str.isdigit, am_part)) or "0"
            afternoon_emoji = ''.join([c for c in pm_part if not c.isdigit() and c != '°'])
            afternoon_temp = ''.join(filter(str.isdigit, pm_part)) or "0"
            return morning_emoji, float(morning_temp), afternoon_emoji, float(afternoon_temp)
        else:
            # fallback
            emoji = summary[0]
            temp = ''.join(filter(str.isdigit, summary)) or "0"
            return emoji, float(temp), emoji, float(temp)
    except Exception:
        emoji = summary[0] if summary else ""
        return emoji, 0.0, emoji, 0.0