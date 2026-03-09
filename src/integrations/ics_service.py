import hashlib
from datetime import date as date_type, datetime, timedelta, timezone
from typing import List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from icalendar import Calendar, Event

from src.models.forecast import Forecast
from src.services.forecast_formatting import (
    MergedWarningWindow, c_to_f, format_detailed_forecast, format_summary,
    get_warning_windows, map_code_to_emoji, merge_overlapping_windows, _fmt_temp,
)


def _stable_uid(date_str: str, location: str) -> str:
    raw = f"{date_str}:{location}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16] + "@weathercal.app"


def _warning_uid(start_time: str, location: str, warning_type: str) -> str:
    raw = f"{start_time}:{location}:{warning_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16] + "@weathercal.app"


def _merged_warning_uid(start_time: str, location: str, warning_types: List[str]) -> str:
    types_key = "+".join(sorted(warning_types))
    raw = f"{start_time}:{location}:{types_key}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16] + "@weathercal.app"


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

    # Single type: show type-specific data
    if len(merged.warning_types) == 1:
        wtype = merged.warning_types[0]
        if wtype == "rain" and rain_in_window:
            lo, hi = round(min(rain_in_window)), round(max(rain_in_window))
            return f"☂️ {lo}–{hi}%"
        if wtype == "wind" and wind_in_window:
            lo, hi = round(min(wind_in_window)), round(max(wind_in_window))
            return f"🌬️ {lo}–{hi} km/h"
        if wtype in ("cold", "snow", "hot", "sunny") and temps_in_window:
            lo = _fmt_temp(min(temps_in_window), unit)
            hi = _fmt_temp(max(temps_in_window), unit)
            return f"{emoji_str} {lo} ~ {hi}°{unit}"

    # Combined types: always show temp range
    if temps_in_window:
        lo = _fmt_temp(min(temps_in_window), unit)
        hi = _fmt_temp(max(temps_in_window), unit)
        return f"{emoji_str} {lo} ~ {hi}°{unit}"

    return emoji_str


def _format_window_description(forecast: Forecast, window, prefs=None) -> str:
    """Format an hourly weather summary for a timed warning event's time range."""
    unit = prefs.get("temp_unit", "C") if prefs else "C"
    start = datetime.fromisoformat(window.start_time)
    end = datetime.fromisoformat(window.end_time)
    lines = []
    for t, temp, code, rain, wind in zip(forecast.times, forecast.temps, forecast.codes, forecast.rain, forecast.winds):
        dt = datetime.fromisoformat(t)
        if dt < start or dt >= end:
            continue
        emoji = map_code_to_emoji(code)
        t_val = _fmt_temp(temp, unit)
        parts = [f"{dt.hour:02d}:00 {emoji} {t_val}°{unit}"]
        if rain and rain >= 40:
            parts.append(f"💧{round(rain)}%")
        if wind and wind >= 30:
            parts.append(f"💨{round(wind)}km/h")
        lines.append("  ".join(parts))

    temps_in_range = [
        temp for t, temp in zip(forecast.times, forecast.temps)
        if start <= datetime.fromisoformat(t) < end
    ]
    if temps_in_range:
        hi = _fmt_temp(max(temps_in_range), unit)
        lo = _fmt_temp(min(temps_in_range), unit)
        lines.append(f"\nHigh: {hi}°{unit} | Low: {lo}°{unit}")
    return "\n".join(lines)


def generate_ics(forecasts: List[Forecast], location_name: str, prefs=None, settings_url: str = None) -> bytes:
    """Generate an ICS calendar bytes from a list of Forecast objects."""
    city = location_name.split(",")[0].strip() if "," in location_name else location_name

    cal = Calendar()
    cal.add("prodid", "-//WeatherCal//weathercal.app//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("X-WR-CALNAME", f"WeatherCal \u2014 {city}")
    cal.add("X-WR-CALDESC", f"Weather forecast for {city} from WeatherCal")
    cal.add("REFRESH-INTERVAL;VALUE=DURATION", "PT12H")
    cal.add("X-PUBLISHED-TTL", "PT12H")

    now = datetime.now(timezone.utc)

    for forecast in forecasts:
        try:
            event_date = date_type.fromisoformat(forecast.date)
        except ValueError:
            continue

        show_allday = prefs.get("show_allday_events", 1) if prefs else 1
        if show_allday:
            event = Event()
            event.add("uid", _stable_uid(forecast.date, forecast.location))
            summary = format_summary(forecast, prefs) if prefs is not None else (forecast.summary or f"Weather: {city}")
            event.add("summary", summary)
            description = format_detailed_forecast(forecast, prefs) if prefs is not None else (forecast.description or "")
            if settings_url:
                description += f"\n\n⚙️ Change your settings: {settings_url}"
            event.add("description", description)
            event.add("location", forecast.location)
            event.add("dtstart", event_date)
            event.add("dtend", event_date + timedelta(days=1))
            event.add("transp", "TRANSPARENT")
            event.add("dtstamp", now)
            cal.add_component(event)

        # Timed warning events
        try:
            tz = ZoneInfo(forecast.timezone) if forecast.timezone else timezone.utc
        except ZoneInfoNotFoundError:
            tz = timezone.utc

        timed_enabled = prefs.get("timed_events_enabled", 1) if prefs else 1
        if timed_enabled:
            windows = get_warning_windows(forecast, prefs)
            merged_windows = merge_overlapping_windows(windows)
            for merged in merged_windows:
                w_event = Event()
                w_event.add("uid", _merged_warning_uid(merged.start_time, forecast.location, merged.warning_types))
                summary = _merged_window_summary(merged, forecast, prefs)
                w_event.add("summary", summary)
                w_event.add("dtstart", datetime.fromisoformat(merged.start_time).replace(tzinfo=tz))
                w_event.add("dtend", datetime.fromisoformat(merged.end_time).replace(tzinfo=tz))
                w_event.add("transp", "TRANSPARENT")
                w_event.add("dtstamp", now)
                description = _format_window_description(forecast, merged, prefs)
                if settings_url:
                    description += f"\n\n⚙️ Change your settings: {settings_url}"
                w_event.add("description", description)
                cal.add_component(w_event)

    cal.add_missing_timezones()
    return cal.to_ical()
