"""Single source of truth: forecast + prefs → list of CalendarEvents.

Both ICS generation and Google Calendar push consume this builder,
ensuring identical event logic regardless of output format.
"""

import hashlib
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date as date_type, datetime, timedelta, timezone
from typing import List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.models.forecast import Forecast
from src.constants import COLD_TEMP_THRESHOLD, HOT_TEMP_THRESHOLD
from src.services.forecast_formatting import (
    MergedWarningWindow,
    _fmt_temp,
    c_to_f,
    format_detailed_forecast,
    format_summary,
    get_warning_windows,
    map_code_to_emoji,
    merge_overlapping_windows,
)


@dataclass
class CalendarEvent:
    uid: str                       # @weathercal.app UID
    summary: str
    description: str
    location: str
    is_allday: bool
    start: date_type | datetime    # date for all-day, tz-aware datetime for timed
    end: date_type | datetime
    transparency: str = "transparent"
    reminder_minutes: int | None = None
    reminder_minutes_evening: int | None = None


# --- UID helpers ---

def stable_uid(date_str: str, location: str) -> str:
    raw = f"{date_str}:{location}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16] + "@weathercal.app"


def warning_uid(start_time: str, location: str, warning_type: str) -> str:
    raw = f"{start_time}:{location}:{warning_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16] + "@weathercal.app"


def merged_warning_uid(start_time: str, location: str, warning_types: List[str]) -> str:
    types_key = "+".join(sorted(warning_types))
    raw = f"{start_time}:{location}:{types_key}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16] + "@weathercal.app"


# --- Formatting helpers ---

def _merged_window_summary(merged: MergedWarningWindow, forecast: Forecast, prefs=None) -> str:
    """Build a contextual summary for a merged warning window."""
    unit = prefs.get("temp_unit", "C") if prefs else "C"
    start = datetime.fromisoformat(merged.start_time)
    end = datetime.fromisoformat(merged.end_time)

    temps_in_window = [
        t for slot, t in zip(forecast.times, forecast.temps)
        if start <= datetime.fromisoformat(slot) < end and t is not None
    ]
    rain_in_window = [
        r for slot, r in zip(forecast.times, forecast.rain)
        if start <= datetime.fromisoformat(slot) < end and r is not None
    ]
    wind_in_window = [
        w for slot, w in zip(forecast.times, forecast.winds)
        if start <= datetime.fromisoformat(slot) < end and w is not None
    ]

    emoji_str = "".join(merged.emojis)

    precip_in_window = [
        p for slot, p in zip(forecast.times, forecast.precipitation or [])
        if start <= datetime.fromisoformat(slot) < end and p is not None
    ]

    # Single type: show type-specific data
    if len(merged.warning_types) == 1:
        wtype = merged.warning_types[0]
        if wtype == "rain" and precip_in_window:
            total_mm = sum(precip_in_window)
            return f"\u2602\ufe0f {total_mm:.1f}mm"
        if wtype == "wind" and wind_in_window:
            peak = round(max(wind_in_window))
            return f"\U0001f32c\ufe0f {peak} km/h"
        if wtype in ("cold", "snow", "hot", "sunny") and temps_in_window:
            lo = _fmt_temp(min(temps_in_window), unit)
            hi = _fmt_temp(max(temps_in_window), unit)
            if lo == hi:
                return f"{emoji_str} {lo}\u00b0{unit}"
            return f"{emoji_str} {lo} ~ {hi}\u00b0{unit}"

    # Combined types: scope temp range to cold/hot hours when present
    if temps_in_window:
        display_temps = temps_in_window
        if "cold" in merged.warning_types and len(merged.warning_types) > 1:
            cold_threshold = prefs.get("cold_threshold", COLD_TEMP_THRESHOLD) if prefs else COLD_TEMP_THRESHOLD
            cold_temps = [t for t in temps_in_window if t < cold_threshold]
            if cold_temps:
                display_temps = cold_temps
        elif "hot" in merged.warning_types and len(merged.warning_types) > 1:
            hot_threshold = prefs.get("hot_threshold", HOT_TEMP_THRESHOLD) if prefs else HOT_TEMP_THRESHOLD
            hot_temps = [t for t in temps_in_window if t > hot_threshold]
            if hot_temps:
                display_temps = hot_temps
        lo = _fmt_temp(min(display_temps), unit)
        hi = _fmt_temp(max(display_temps), unit)
        if lo == hi:
            return f"{emoji_str} {lo}\u00b0{unit}"
        return f"{emoji_str} {lo} ~ {hi}\u00b0{unit}"

    return emoji_str


def _format_window_description(forecast: Forecast, window, prefs=None) -> str:
    """Format a compact weather summary for a timed warning event."""
    unit = prefs.get("temp_unit", "C") if prefs else "C"
    start = datetime.fromisoformat(window.start_time)
    end = datetime.fromisoformat(window.end_time)

    temps, precips, chances, winds, codes = [], [], [], [], []
    precip_list = forecast.precipitation or [0] * len(forecast.times)
    for t, temp, code, rain, wind, precip in zip(
        forecast.times, forecast.temps, forecast.codes, forecast.rain,
        forecast.winds, precip_list
    ):
        dt = datetime.fromisoformat(t)
        if dt < start or dt >= end:
            continue
        if temp is not None:
            temps.append(temp)
        if code is not None:
            codes.append(code)
        if precip is not None and precip > 0:
            precips.append(precip)
        if rain is not None and rain > 0:
            chances.append(round(rain))
        if wind is not None:
            winds.append(wind)

    lines = []
    warning_types = getattr(window, "warning_types", [])

    # Precipitation line — snowflake for snow, weather emoji otherwise
    if precips:
        if "snow" in warning_types:
            emoji = "\u2744\ufe0f"
        else:
            dominant_code = Counter(codes).most_common(1)[0][0] if codes else 0
            emoji = map_code_to_emoji(dominant_code)
        total = sum(precips)
        if chances:
            lo_ch, hi_ch = min(chances), max(chances)
            ch_str = f"{lo_ch}%" if lo_ch == hi_ch else f"{lo_ch}\u2013{hi_ch}%"
            lines.append(f"{emoji} {total:.1f}mm total ({ch_str})")
        else:
            lines.append(f"{emoji} {total:.1f}mm total")

    # Wind line — only if notable (>= 30 km/h)
    strong_winds = [w for w in winds if w >= 30]
    if strong_winds:
        peak = round(max(strong_winds))
        lines.append(f"\U0001f4a8 Gusts to {peak} km/h")

    # Temperature line — 🥶 for cold, 🥵 for hot, 🌡️ otherwise
    if temps:
        if "cold" in warning_types:
            temp_emoji = "\U0001f976"
        elif "hot" in warning_types:
            temp_emoji = "\U0001f975"
        else:
            temp_emoji = "\U0001f321\ufe0f"
        lo = _fmt_temp(min(temps), unit)
        hi = _fmt_temp(max(temps), unit)
        if lo == hi:
            lines.append(f"{temp_emoji} {lo}\u00b0{unit}")
        else:
            lines.append(f"{temp_emoji} {lo} ~ {hi}\u00b0{unit}")

    return "\n".join(lines)


# --- Main builder ---

def build_calendar_events(forecast: Forecast, prefs=None, settings_url: str = None) -> list[CalendarEvent]:
    """Single source of truth: forecast + prefs -> list of CalendarEvents."""
    events = []

    try:
        event_date = date_type.fromisoformat(forecast.date)
    except ValueError:
        return events

    try:
        tz = ZoneInfo(forecast.timezone) if forecast.timezone else timezone.utc
    except ZoneInfoNotFoundError:
        tz = timezone.utc

    # Resolve temperature display: feels-like or actual
    if prefs and prefs.get("temp_display", "feels_like") == "feels_like" and forecast.apparent_temps:
        forecast = replace(forecast, temps=forecast.apparent_temps)

    # Reminder preferences
    allday_reminder_hour = prefs.get("reminder_allday_hour", -1) if prefs else -1
    evening_reminder_hour = prefs.get("reminder_evening_hour", -1) if prefs else -1
    timed_reminder_mins = prefs.get("reminder_timed_minutes", -1) if prefs else -1

    # All-day event
    show_allday = prefs.get("show_allday_events", 1) if prefs else 1
    if show_allday:
        summary = format_summary(forecast, prefs) if prefs is not None else (forecast.summary or f"Weather: {forecast.location}")
        description = format_detailed_forecast(forecast, prefs) if prefs is not None else (forecast.description or "")
        if settings_url:
            description += f"\n\n\u2699\ufe0f {settings_url}"
            description += "\n\u2709\ufe0f hello@weathercal.app"
        events.append(CalendarEvent(
            uid=stable_uid(forecast.date, forecast.location),
            summary=summary,
            description=description,
            location=forecast.location,
            is_allday=True,
            start=event_date,
            end=event_date + timedelta(days=1),
            reminder_minutes=allday_reminder_hour * 60 if allday_reminder_hour >= 0 else None,
            reminder_minutes_evening=(24 - evening_reminder_hour) * 60 if evening_reminder_hour >= 0 else None,
        ))

    # Timed warning events
    timed_enabled = prefs.get("timed_events_enabled", 1) if prefs else 1
    if timed_enabled:
        windows = get_warning_windows(forecast, prefs)
        merged_windows = merge_overlapping_windows(windows)
        for merged in merged_windows:
            summary = _merged_window_summary(merged, forecast, prefs)
            description = _format_window_description(forecast, merged, prefs)
            if settings_url:
                description += f"\n\n\u2699\ufe0f {settings_url}"
                description += "\n\u2709\ufe0f hello@weathercal.app"
            events.append(CalendarEvent(
                uid=merged_warning_uid(merged.start_time, forecast.location, merged.warning_types),
                summary=summary,
                description=description,
                location=forecast.location,
                is_allday=False,
                start=datetime.fromisoformat(merged.start_time).replace(tzinfo=tz),
                end=datetime.fromisoformat(merged.end_time).replace(tzinfo=tz),
                reminder_minutes=timed_reminder_mins if timed_reminder_mins >= 0 else None,
            ))

    return events
