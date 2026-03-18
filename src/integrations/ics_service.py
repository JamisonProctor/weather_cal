from datetime import date, datetime, timedelta, timezone
from typing import List

from icalendar import Alarm, Calendar, Event

from src.models.forecast import Forecast
from src.services.calendar_events import (
    CalendarEvent,
    build_calendar_events,
    merged_warning_uid,
    stable_uid,
    warning_uid,
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
            if ce.reminder_minutes_evening is not None and ce.reminder_minutes_evening >= 0:
                alarm = Alarm()
                alarm.add("action", "DISPLAY")
                alarm.add("description", ce.summary)
                alarm.add("trigger", timedelta(minutes=-ce.reminder_minutes_evening))
                event.add_component(alarm)
            if ce.reminder_minutes is not None and ce.reminder_minutes >= 0:
                alarm = Alarm()
                alarm.add("action", "DISPLAY")
                alarm.add("description", ce.summary)
                if ce.is_allday:
                    alarm.add("trigger", timedelta(hours=ce.reminder_minutes // 60))
                else:
                    alarm.add("trigger", timedelta(minutes=-ce.reminder_minutes))
                event.add_component(alarm)
            cal.add_component(event)

    cal.add_missing_timezones()
    return cal.to_ical()


def generate_google_active_ics(settings_url: str) -> bytes:
    """Return a minimal ICS indicating weather is synced via Google Calendar."""
    cal = Calendar()
    cal.add("prodid", "-//WeatherCal//weathercal.app//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("X-WR-CALNAME", "WeatherCal")
    cal.add("REFRESH-INTERVAL;VALUE=DURATION", "PT12H")
    cal.add("X-PUBLISHED-TTL", "PT12H")

    today = date.today()
    now = datetime.now(timezone.utc)

    event = Event()
    event.add("uid", "google-active@weathercal.app")
    event.add("summary", "⚠️👋 WeatherCal moved to Google Calendar")
    event.add(
        "description",
        "Your weather forecast is being delivered directly to Google Calendar.\n\n"
        "You can safely remove this calendar subscription.\n\n"
        f"Manage your connection: {settings_url}",
    )
    event.add("dtstart", today)
    event.add("dtend", today)
    event.add("transp", "TRANSPARENT")
    event.add("dtstamp", now)
    cal.add_component(event)

    return cal.to_ical()
