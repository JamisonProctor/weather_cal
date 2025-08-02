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