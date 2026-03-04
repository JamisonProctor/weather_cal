import hashlib
from datetime import date as date_type, datetime, timedelta, timezone
from typing import List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from icalendar import Calendar, Event

from src.models.forecast import Forecast
from src.services.forecast_formatting import format_summary, get_warning_windows


def _stable_uid(date_str: str, location: str) -> str:
    raw = f"{date_str}:{location}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16] + "@weathercal.app"


def _warning_uid(start_time: str, location: str, warning_type: str) -> str:
    raw = f"{start_time}:{location}:{warning_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16] + "@weathercal.app"


def _sunny_summary(window, forecast) -> str:
    try:
        start = datetime.fromisoformat(window.start_time)
        end = datetime.fromisoformat(window.end_time)
        temps_in_window = [
            t for slot, t in zip(forecast.times, forecast.temps)
            if start <= datetime.fromisoformat(slot) <= end
        ]
        if temps_in_window:
            return f"☀️ {round(min(temps_in_window))}–{round(max(temps_in_window))}°C"
    except Exception:
        pass
    return f"{window.emoji} {window.label}"


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
            description = forecast.description or ""
            if settings_url:
                description += f"\n\n⚙️ Change your settings: {settings_url}"
            event.add("description", description)
            event.add("location", forecast.location)
            event.add("dtstart", event_date)
            event.add("dtend", event_date + timedelta(days=1))
            event.add("transp", "TRANSPARENT")
            event.add("dtstamp", now)
            if settings_url:
                event.add("url", settings_url)
            cal.add_component(event)

        # Timed warning events
        try:
            tz = ZoneInfo(forecast.timezone) if forecast.timezone else timezone.utc
        except ZoneInfoNotFoundError:
            tz = timezone.utc

        timed_enabled = prefs.get("timed_events_enabled", 1) if prefs else 1
        if timed_enabled:
            for window in get_warning_windows(forecast, prefs):
                w_event = Event()
                w_event.add("uid", _warning_uid(window.start_time, forecast.location, window.warning_type))
                if window.warning_type == "sunny":
                    summary = _sunny_summary(window, forecast)
                else:
                    summary = f"{window.emoji} {window.label}"
                w_event.add("summary", summary)
                w_event.add("dtstart", datetime.fromisoformat(window.start_time).replace(tzinfo=tz))
                w_event.add("dtend", datetime.fromisoformat(window.end_time).replace(tzinfo=tz))
                w_event.add("transp", "TRANSPARENT")
                w_event.add("dtstamp", now)
                if settings_url:
                    w_event.add("description", f"⚙️ Change your settings: {settings_url}")
                    w_event.add("url", settings_url)
                cal.add_component(w_event)

    return cal.to_ical()
