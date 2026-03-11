# forecast_formatting.py

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean
from typing import List, Tuple

from src.models.forecast import Forecast

SNOW_WARNING_CODES = {71, 73, 75, 77, 85, 86}
SUNNY_CODES = {0, 1, 2}
RAIN_MM_THRESHOLD = 0.5
WIND_SPEED_THRESHOLD = 30
COLD_TEMP_THRESHOLD = 3
HOT_TEMP_THRESHOLD = 28
WARM_TEMP_THRESHOLD = 14
MIN_SUNNY_HOURS = 2

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
      - No hazards: 'AM🌧️15° / PM☁️16°'
      - With hazards: '⚠️☂️🌬️ AM6° / 13°'
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
        return f"⚠️{warnings} AM{morning_value}° / {afternoon_value}°"

    return f"AM{morning_emoji}{morning_value}° / PM{afternoon_emoji}{afternoon_value}°"

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
    warning_types: List[str]    # e.g. ["rain", "cold"] — ordered by _WARNING_CHECKS
    emojis: List[str]           # e.g. ["☂️", "🥶"]
    start_time: str             # min of all overlapping starts
    end_time: str               # max of all overlapping ends


_WARNING_CHECKS = [
    (
        "rain", "☂️", "Rain Warning",
        lambda temp, code, rain, wind, precip: (precip or 0) >= RAIN_MM_THRESHOLD,
    ),
    (
        "wind", "🌬️", "Wind Warning",
        lambda temp, code, rain, wind, precip: (wind or 0) >= WIND_SPEED_THRESHOLD,
    ),
    (
        "cold", "🥶", "Cold Warning",
        lambda temp, code, rain, wind, precip: (temp is not None) and temp < COLD_TEMP_THRESHOLD,
    ),
    (
        "snow", "☃️", "Snow Warning",
        lambda temp, code, rain, wind, precip: code in SNOW_WARNING_CODES,
    ),
    (
        "sunny", "☀️", "Nice weather — enjoy!",
        lambda temp, code, rain, wind, precip: code in SUNNY_CODES
        and (temp is not None) and temp >= WARM_TEMP_THRESHOLD
        and (precip or 0) < RAIN_MM_THRESHOLD
        and (wind or 0) < WIND_SPEED_THRESHOLD,
    ),
    (
        "hot", "🥵", "Heat Warning",
        lambda temp, code, rain, wind, precip: (temp is not None) and temp > HOT_TEMP_THRESHOLD,
    ),
]


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

    for wtype, emoji, label, check in _WARNING_CHECKS:
        # Opt-in types (sunny, hot): skip unless prefs explicitly enables them
        if wtype in ("sunny", "hot") and (prefs is None or not prefs.get(f"warn_{wtype}", 0)):
            continue
        # Opt-out types: skip if prefs explicitly disables them
        if prefs is not None and wtype not in ("sunny", "hot") and not prefs.get(f"warn_{wtype}", 1):
            continue

        if wtype == "cold" and prefs is not None:
            ct = prefs.get("cold_threshold", COLD_TEMP_THRESHOLD)
            active_check = lambda temp, code, rain, wind, precip, ct=ct: (temp is not None) and temp < ct
        elif wtype == "hot" and prefs is not None:
            ht = prefs.get("hot_threshold", HOT_TEMP_THRESHOLD)
            active_check = lambda temp, code, rain, wind, precip, ht=ht: (temp is not None) and temp > ht
        elif wtype == "sunny" and prefs is not None:
            wt = prefs.get("warm_threshold", WARM_TEMP_THRESHOLD)
            active_check = lambda temp, code, rain, wind, precip, wt=wt: (
                code in SUNNY_CODES
                and (temp is not None) and temp >= wt
                and (precip or 0) < RAIN_MM_THRESHOLD
                and (wind or 0) < WIND_SPEED_THRESHOLD
            )
        else:
            active_check = check

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


_TYPE_ORDER = {wtype: i for i, (wtype, *_) in enumerate(_WARNING_CHECKS)}


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


def format_detailed_forecast(forecast: Forecast, prefs=None) -> str:
    """
    Returns a multiline string with detailed forecast information,
    grouped by core daypart start hours (6, 9, 12, 15, 18, 21).
    Each line shows time, dominant emoji, temperature range, and optional warning icons.
    Final line summarizes daily high/low.
    """
    unit = prefs.get("temp_unit", "C") if prefs else "C"
    slots = [6, 9, 12, 15, 18, 21]
    description_lines = []
    data = list(zip(forecast.times, forecast.temps, forecast.codes, forecast.rain,
                    forecast.winds, forecast.precipitation or [0]*len(forecast.times)))
    for start in slots:
        block = [d for d in data if datetime.fromisoformat(d[0]).hour in (start, start+1, start+2)]
        if not block:
            continue
        start_temp = _fmt_temp(block[0][1], unit)
        mid_temp = _fmt_temp(block[-1][1], unit) if len(block) > 1 else start_temp
        dominant_code = Counter([d[2] for d in block]).most_common(1)[0][0]
        emoji = map_code_to_emoji(dominant_code)
        warnings = _collect_warnings(block, prefs)
        line = f"{start:02d}:00 {emoji} {start_temp}°~{mid_temp}°{unit}"
        if warnings:
            line += f" ⚠️{warnings}"
        description_lines.append(line)
    high = _fmt_temp(forecast.high, unit)
    low = _fmt_temp(forecast.low, unit)
    description_lines.append(f"\nHigh: {high}°{unit} | Low: {low}°{unit}")
    return "\n".join(description_lines)
