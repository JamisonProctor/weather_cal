# forecast_formatting.py

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean
from typing import List, Tuple

from src.models.forecast import Forecast

RAIN_WARNING_CODES = {
    51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99
}
SNOW_WARNING_CODES = {71, 73, 75, 77, 85, 86}
RAIN_PROB_THRESHOLD = 40
WIND_SPEED_THRESHOLD = 30
COLD_TEMP_THRESHOLD = 3

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
    Returns a concise summary string for the calendar event title.
    Example outputs:
      - No hazards: 'AM🌧️15° / PM☁️16°'
      - With hazards: '⚠️☂️🌬️ AM6° / 13°'
    """
    morning_emoji, morning_temp, afternoon_emoji, afternoon_temp = map_morning_afternoon(
        forecast.times, forecast.temps, forecast.codes
    )
    data = list(zip(forecast.times, forecast.temps, forecast.codes, forecast.rain, forecast.winds))
    warnings = _collect_warnings(data) if data else ""

    morning_value = round(morning_temp)
    afternoon_value = round(afternoon_temp)

    if warnings:
        return f"⚠️{warnings} AM{morning_value}° / {afternoon_value}°"

    return f"AM{morning_emoji}{morning_value}° / PM{afternoon_emoji}{afternoon_value}°"

def _collect_warnings(block: List[Tuple[str, float, int, float, float]]) -> str:
    """
    Return concatenated warning icons for a time block based on precipitation,
    snow, wind, and cold temperatures.
    """
    rain_vals = [value for value in (d[3] for d in block) if value is not None]
    wind_vals = [value for value in (d[4] for d in block) if value is not None]
    temps = [value for value in (d[1] for d in block) if value is not None]
    codes = [d[2] for d in block if d[2] is not None]

    warnings: List[str] = []
    max_rain = max(rain_vals) if rain_vals else 0
    max_wind = max(wind_vals) if wind_vals else 0

    is_rainy = max_rain >= RAIN_PROB_THRESHOLD or any(code in RAIN_WARNING_CODES for code in codes)
    if is_rainy:
        warnings.append("☂️")

    if max_wind >= WIND_SPEED_THRESHOLD:
        warnings.append("🌬️")

    if temps and min(temps) < COLD_TEMP_THRESHOLD:
        warnings.append("🥶")

    if any(code in SNOW_WARNING_CODES for code in codes):
        warnings.append("☃️")

    return "".join(warnings)


@dataclass
class WarningWindow:
    """A contiguous time block during which a weather warning condition is active."""
    warning_type: str   # "rain", "wind", "cold", "snow"
    emoji: str          # e.g. "☂️"
    label: str          # e.g. "Rain Warning"
    start_time: str     # ISO datetime e.g. "2025-08-01T10:00"
    end_time: str       # ISO datetime e.g. "2025-08-01T14:00" (exclusive — last active hour + 1h)


_WARNING_CHECKS = [
    (
        "rain", "☂️", "Rain Warning",
        lambda temp, code, rain, wind: (rain or 0) >= RAIN_PROB_THRESHOLD or code in RAIN_WARNING_CODES,
    ),
    (
        "wind", "🌬️", "Wind Warning",
        lambda temp, code, rain, wind: (wind or 0) >= WIND_SPEED_THRESHOLD,
    ),
    (
        "cold", "🥶", "Cold Warning",
        lambda temp, code, rain, wind: (temp is not None) and temp < COLD_TEMP_THRESHOLD,
    ),
    (
        "snow", "☃️", "Snow Warning",
        lambda temp, code, rain, wind: code in SNOW_WARNING_CODES,
    ),
]


def get_warning_windows(forecast: Forecast) -> List[WarningWindow]:
    """
    Return a list of WarningWindow objects for each contiguous block of hours
    where a warning condition (rain, wind, cold, snow) is active.
    Each warning type is evaluated independently, so overlapping windows of
    different types are possible.
    """
    data = list(zip(forecast.times, forecast.temps, forecast.codes, forecast.rain, forecast.winds))
    windows: List[WarningWindow] = []

    for wtype, emoji, label, check in _WARNING_CHECKS:
        run_start = None
        run_last = None

        for t, temp, code, rain, wind in data:
            if check(temp, code, rain, wind):
                if run_start is None:
                    run_start = t
                run_last = t
            else:
                if run_start is not None:
                    end_dt = datetime.fromisoformat(run_last) + timedelta(hours=1)
                    windows.append(WarningWindow(
                        warning_type=wtype,
                        emoji=emoji,
                        label=label,
                        start_time=run_start,
                        end_time=end_dt.strftime("%Y-%m-%dT%H:%M"),
                    ))
                    run_start = None
                    run_last = None

        if run_start is not None:
            end_dt = datetime.fromisoformat(run_last) + timedelta(hours=1)
            windows.append(WarningWindow(
                warning_type=wtype,
                emoji=emoji,
                label=label,
                start_time=run_start,
                end_time=end_dt.strftime("%Y-%m-%dT%H:%M"),
            ))

    return windows


def format_detailed_forecast(forecast: Forecast) -> str:
    """
    Returns a multiline string with detailed forecast information,
    grouped by core daypart start hours (6, 9, 12, 15, 18, 21).
    Each line shows time, dominant emoji, temperature range, and optional warning icons.
    Final line summarizes daily high/low.
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
        warnings = _collect_warnings(block)
        line = f"{start:02d}:00 {emoji} {start_temp}°~{mid_temp}°C"
        if warnings:
            line += f" ⚠️{warnings}"
        description_lines.append(line)
    description_lines.append(f"\nHigh: {forecast.high}°C | Low: {forecast.low}°C")
    return "\n".join(description_lines)
