# forecast_formatting.py

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean
from typing import List, Tuple

from src.constants import (
    COLD_TEMP_THRESHOLD,
    HOT_TEMP_THRESHOLD,
    MIN_SUNNY_HOURS,
    RAIN_MM_THRESHOLD,
    SNOW_WARNING_CODES,
    SUNNY_CODES,
    WARM_TEMP_THRESHOLD,
    WIND_SPEED_THRESHOLD,
)
from src.models.forecast import Forecast

def c_to_f(temp: float) -> float:
    return temp * 9 / 5 + 32

def _fmt_temp(temp: float, unit: str) -> int:
    return round(c_to_f(temp) if unit == "F" else temp)

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

def format_summary(forecast: Forecast, prefs=None) -> str:
    """
    Returns a concise summary string for the calendar event title.
    Example outputs:
      - No hazards: '🌧️15° → ☁️16°'
      - With hazards: '⚠️☂️🌬️ 6° → 13°'
    """
    morning_emoji, morning_temp, afternoon_emoji, afternoon_temp = map_morning_afternoon(
        forecast.times, forecast.temps, forecast.codes
    )
    data = list(zip(forecast.times, forecast.temps, forecast.codes, forecast.rain,
                    forecast.winds, forecast.precipitation or [0]*len(forecast.times)))
    warnings = _collect_warnings(data, prefs) if data else ""

    unit = prefs.get("temp_unit", "C") if prefs else "C"
    morning_value = _fmt_temp(morning_temp, unit)
    afternoon_value = _fmt_temp(afternoon_temp, unit)

    if warnings:
        return f"⚠️{warnings} {morning_value}° → {afternoon_value}°"

    return f"{morning_emoji}{morning_value}° → {afternoon_emoji}{afternoon_value}°"

def _collect_warnings(block: List[Tuple[str, float, int, float, float, float]], prefs=None) -> str:
    """
    Return concatenated warning icons for a time block based on precipitation,
    snow, wind, and cold temperatures. Respects user prefs if provided.
    """
    if prefs is not None and not prefs.get("warn_in_allday", 1):
        return ""

    cold_threshold = prefs.get("cold_threshold", COLD_TEMP_THRESHOLD) if prefs is not None else COLD_TEMP_THRESHOLD

    precip_vals = [value for value in (d[5] for d in block) if value is not None]
    wind_vals = [value for value in (d[4] for d in block) if value is not None]
    temps = [value for value in (d[1] for d in block) if value is not None]
    codes = [d[2] for d in block if d[2] is not None]

    warnings: List[str] = []
    max_precip = max(precip_vals) if precip_vals else 0
    max_wind = max(wind_vals) if wind_vals else 0

    if prefs is None or prefs.get("allday_rain", 1):
        if max_precip >= RAIN_MM_THRESHOLD:
            warnings.append("☂️")

    if prefs is None or prefs.get("allday_wind", 1):
        if max_wind >= WIND_SPEED_THRESHOLD:
            warnings.append("🌬️")

    if prefs is None or prefs.get("allday_cold", 1):
        if temps and min(temps) < cold_threshold:
            warnings.append("🥶")

    if prefs is None or prefs.get("allday_snow", 1):
        if any(code in SNOW_WARNING_CODES for code in codes):
            warnings.append("☃️")

    if prefs is not None and prefs.get("allday_sunny", 0):
        if codes and all(code in SUNNY_CODES for code in codes):
            warnings.append("☀️")

    hot_threshold_val = prefs.get("hot_threshold", HOT_TEMP_THRESHOLD) if prefs is not None else HOT_TEMP_THRESHOLD
    if prefs is not None and prefs.get("allday_hot", 0):
        if temps and max(temps) > hot_threshold_val:
            warnings.append("🥵")

    return "".join(warnings)


@dataclass
class WarningWindow:
    """A contiguous time block during which a weather warning condition is active."""
    warning_type: str   # "rain", "wind", "cold", "snow"
    emoji: str          # e.g. "☂️"
    label: str          # e.g. "Rain Warning"
    start_time: str     # ISO datetime e.g. "2025-08-01T10:00"
    end_time: str       # ISO datetime e.g. "2025-08-01T14:00" (exclusive — last active hour + 1h)


@dataclass
class MergedWarningWindow:
    """One or more overlapping WarningWindows merged into a single calendar event."""
    warning_types: List[str]    # e.g. ["rain", "cold"] — ordered by _WARNING_TYPES
    emojis: List[str]           # e.g. ["☂️", "🥶"]
    start_time: str             # min of all overlapping starts
    end_time: str               # max of all overlapping ends


_WARNING_TYPES = [
    ("rain", "☂️", "Rain Warning"),
    ("wind", "🌬️", "Wind Warning"),
    ("cold", "🥶", "Cold Warning"),
    ("snow", "☃️", "Snow Warning"),
    ("sunny", "☀️", "Nice weather — enjoy!"),
    ("hot", "🥵", "Heat Warning"),
]


def _make_check(wtype: str, prefs=None):
    """Build the check lambda for a warning type, respecting user prefs for thresholds."""
    if wtype == "rain":
        return lambda temp, code, rain, wind, precip: (precip or 0) >= RAIN_MM_THRESHOLD
    if wtype == "wind":
        return lambda temp, code, rain, wind, precip: (wind or 0) >= WIND_SPEED_THRESHOLD
    if wtype == "cold":
        ct = prefs.get("cold_threshold", COLD_TEMP_THRESHOLD) if prefs else COLD_TEMP_THRESHOLD
        return lambda temp, code, rain, wind, precip, ct=ct: (temp is not None) and temp < ct
    if wtype == "snow":
        return lambda temp, code, rain, wind, precip: code in SNOW_WARNING_CODES
    if wtype == "sunny":
        wt = prefs.get("warm_threshold", WARM_TEMP_THRESHOLD) if prefs else WARM_TEMP_THRESHOLD
        return lambda temp, code, rain, wind, precip, wt=wt: (
            code in SUNNY_CODES
            and (temp is not None) and temp >= wt
            and (precip or 0) < RAIN_MM_THRESHOLD
            and (wind or 0) < WIND_SPEED_THRESHOLD
        )
    if wtype == "hot":
        ht = prefs.get("hot_threshold", HOT_TEMP_THRESHOLD) if prefs else HOT_TEMP_THRESHOLD
        return lambda temp, code, rain, wind, precip, ht=ht: (temp is not None) and temp > ht
    raise ValueError(f"Unknown warning type: {wtype}")


def get_warning_windows(forecast: Forecast, prefs=None) -> List[WarningWindow]:
    """
    Return a list of WarningWindow objects for each contiguous block of hours
    where a warning condition (rain, wind, cold, snow, sunny) is active.
    Each warning type is evaluated independently, so overlapping windows of
    different types are possible. Respects user prefs if provided.
    """
    data = list(zip(forecast.times, forecast.temps, forecast.codes, forecast.rain,
                    forecast.winds, forecast.precipitation or [0]*len(forecast.times)))
    windows: List[WarningWindow] = []

    for wtype, emoji, label in _WARNING_TYPES:
        # Opt-in types (sunny, hot): skip unless prefs explicitly enables them
        if wtype in ("sunny", "hot") and (prefs is None or not prefs.get(f"warn_{wtype}", 0)):
            continue
        # Opt-out types: skip if prefs explicitly disables them
        if prefs is not None and wtype not in ("sunny", "hot") and not prefs.get(f"warn_{wtype}", 1):
            continue

        active_check = _make_check(wtype, prefs)
        run_start = None
        run_last = None

        for t, temp, code, rain, wind, precip in data:
            if active_check(temp, code, rain, wind, precip):
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

    windows = [
        w for w in windows
        if w.warning_type != "sunny"
        or (datetime.fromisoformat(w.end_time) - datetime.fromisoformat(w.start_time)) >= timedelta(hours=MIN_SUNNY_HOURS)
    ]

    return windows


_TYPE_ORDER = {wtype: i for i, (wtype, *_) in enumerate(_WARNING_TYPES)}


def merge_overlapping_windows(windows: List[WarningWindow]) -> List[MergedWarningWindow]:
    """Merge overlapping WarningWindows into combined MergedWarningWindows."""
    if not windows:
        return []

    intervals = []
    for w in windows:
        start_dt = datetime.fromisoformat(w.start_time)
        end_dt = datetime.fromisoformat(w.end_time)
        intervals.append((start_dt, end_dt, w))

    intervals.sort(key=lambda x: x[0])

    merged: List[MergedWarningWindow] = []
    cur_start, cur_end = intervals[0][0], intervals[0][1]
    cur_types = {intervals[0][2].warning_type: intervals[0][2].emoji}

    for start_dt, end_dt, w in intervals[1:]:
        if start_dt < cur_end:  # strict overlap
            cur_end = max(cur_end, end_dt)
            cur_types[w.warning_type] = w.emoji
        else:
            ordered = sorted(cur_types.items(), key=lambda x: _TYPE_ORDER.get(x[0], 99))
            merged.append(MergedWarningWindow(
                warning_types=[t for t, _ in ordered],
                emojis=[e for _, e in ordered],
                start_time=cur_start.strftime("%Y-%m-%dT%H:%M"),
                end_time=cur_end.strftime("%Y-%m-%dT%H:%M"),
            ))
            cur_start, cur_end = start_dt, end_dt
            cur_types = {w.warning_type: w.emoji}

    ordered = sorted(cur_types.items(), key=lambda x: _TYPE_ORDER.get(x[0], 99))
    merged.append(MergedWarningWindow(
        warning_types=[t for t, _ in ordered],
        emojis=[e for _, e in ordered],
        start_time=cur_start.strftime("%Y-%m-%dT%H:%M"),
        end_time=cur_end.strftime("%Y-%m-%dT%H:%M"),
    ))

    return merged


DAYPART_BLOCKS = [
    ("Morning", range(6, 10)),
    ("Midday", range(10, 14)),
    ("Afternoon", range(14, 18)),
    ("Evening", range(18, 21)),
    ("Night", range(21, 24)),
]


def format_detailed_forecast(forecast: Forecast, prefs=None) -> str:
    """
    Returns a multiline string with detailed forecast information,
    grouped by named dayparts (Morning, Midday, Afternoon, Evening, Night).
    Each line shows the daypart label, dominant emoji, average temperature,
    and optional warning icons.
    """
    unit = prefs.get("temp_unit", "C") if prefs else "C"
    description_lines = []
    data = list(zip(forecast.times, forecast.temps, forecast.codes, forecast.rain,
                    forecast.winds, forecast.precipitation or [0]*len(forecast.times)))
    for label, hour_range in DAYPART_BLOCKS:
        block = [d for d in data if datetime.fromisoformat(d[0]).hour in hour_range]
        if not block:
            continue
        avg_temp = _fmt_temp(mean([d[1] for d in block]), unit)
        dominant_code = Counter([d[2] for d in block]).most_common(1)[0][0]
        emoji = map_code_to_emoji(dominant_code)
        warnings = _collect_warnings(block, prefs)
        line = f"{label} {emoji} {avg_temp}°{unit}"
        if warnings:
            line += f" ⚠️{warnings}"
        description_lines.append(line)
    return "\n".join(description_lines)
