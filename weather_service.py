import requests
from datetime import datetime
from statistics import mean

import os
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

from collections import Counter

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
        "hourly": "temperature_2m,weathercode",
        "timezone": "Europe/Berlin",
        "forecast_days": 7,
    }

    response = requests.get(OPEN_METEO_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    times = data["hourly"]["time"]
    temps = data["hourly"]["temperature_2m"]
    codes = data["hourly"]["weathercode"]

    daily_data = {}

    for t, temp, code in zip(times, temps, codes):
        dt = datetime.fromisoformat(t)
        date_str = dt.date().isoformat()

        # Focus on daytime only
        if 6 <= dt.hour <= 22:
            if date_str not in daily_data:
                daily_data[date_str] = {
                    "temps": [],
                    "codes": [],
                    "times": []
                }
            daily_data[date_str]["temps"].append(temp)
            daily_data[date_str]["codes"].append(code)
            daily_data[date_str]["times"].append(t)

    # Convert to list of clean forecasts
    forecasts = []
    for date, vals in daily_data.items():
        high = max(vals["temps"])
        low = min(vals["temps"])
        morning_emoji, morning_temp, afternoon_emoji, afternoon_temp = map_morning_afternoon(vals["times"], vals["temps"], vals["codes"])
        summary = f"{morning_emoji}{round(morning_temp)}° ➡️ {afternoon_emoji}{round(afternoon_temp)}°"

        forecasts.append({
            "date": date,
            "high": round(high),
            "low": round(low),
            "summary": summary
        })

    return forecasts
