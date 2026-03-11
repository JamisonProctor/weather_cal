from datetime import datetime, timezone
from typing import List

from icalendar import Calendar, Event

from src.models.forecast import Forecast
from src.services.calendar_events import (
    CalendarEvent,
    build_calendar_events,
    _format_window_description,
    _merged_warning_uid,
    _merged_window_summary,
    _stable_uid,
    _warning_uid,
)


def generate_ics(forecasts: List[Forecast], location_name: str, prefs=None, settings_url: str = None) -> bytes:
    """Generate an ICS calendar bytes from a list of Forecast objects."""
    city = location_name.split(",")[0].strip() if "," in location_name else location_name

    cal = Calendar()
    cal.add("prodid", "-//WeatherCal//weathercal.app//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("X-WR-CALNAME", "WeatherCal")
    cal.add("X-WR-CALDESC", f"Weather forecast for {city} from WeatherCal")
    cal.add("REFRESH-INTERVAL;VALUE=DURATION", "PT12H")
    cal.add("X-PUBLISHED-TTL", "PT12H")

    now = datetime.now(timezone.utc)

    for forecast in forecasts:
        for ce in build_calendar_events(forecast, prefs, settings_url):
            event = Event()
            event.add("uid", ce.uid)
            event.add("summary", ce.summary)
            event.add("description", ce.description)
            event.add("location", ce.location)
            event.add("dtstart", ce.start)
            event.add("dtend", ce.end)
            event.add("transp", "TRANSPARENT")
            event.add("dtstamp", now)
            cal.add_component(event)

    cal.add_missing_timezones()
    return cal.to_ical()
