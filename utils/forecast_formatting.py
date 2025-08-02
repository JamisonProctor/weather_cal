# forecast_formatting.py

from collections import Counter
from datetime import datetime
from statistics import mean
from forecast import Forecast

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

def map_morning_afternoon(times, temps, codes, start_hour=6, end_hour=22):
    mid_hour = 12  # fixed midday split
    morning = [(temp, code) for t, temp, code in zip(times, temps, codes) if start_hour <= datetime.fromisoformat(t).hour < mid_hour]
    afternoon = [(temp, code) for t, temp, code in zip(times, temps, codes) if mid_hour <= datetime.fromisoformat(t).hour <= end_hour]
    morning_temp = mean([x[0] for x in morning]) if morning else 0
    afternoon_temp = mean([x[0] for x in afternoon]) if afternoon else 0
    morning_emoji = map_code_to_emoji(Counter([x[1] for x in morning]).most_common(1)[0][0]) if morning else ""
    afternoon_emoji = map_code_to_emoji(Counter([x[1] for x in afternoon]).most_common(1)[0][0]) if afternoon else ""
    return morning_emoji, morning_temp, afternoon_emoji, afternoon_temp

def format_summary(forecast: Forecast) -> str:
    """
    Returns a summary string like 'AM🌧️15° / PM☁️16°' for the given Forecast instance.
    """
    morning_emoji, morning_temp, afternoon_emoji, afternoon_temp = map_morning_afternoon(
        forecast.times, forecast.temps, forecast.codes
    )
    return f"AM{morning_emoji}{round(morning_temp)}° / PM{afternoon_emoji}{round(afternoon_temp)}°"

def format_detailed_forecast(forecast: Forecast) -> str:
    """
    Returns a multiline string with detailed forecast information,
    with blocks starting at 6, 9, 12, 15, 18, 21, each line showing:
    time, emoji, temp range, rain %, wind speed
    Ends with high/low summary line.
    """
    slots = [6, 9, 12, 15, 18, 21]
    description_lines = []
    data = list(zip(forecast.times, forecast.temps, forecast.codes, forecast.rain, forecast.winds))
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
    description_lines.append(f"\nHigh: {forecast.high}°C | Low: {forecast.low}°C")
    return "\n".join(description_lines)