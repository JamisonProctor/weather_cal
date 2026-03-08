import hashlib
from datetime import datetime, timezone

from icalendar import Calendar, Event


def _event_uid(external_key: str) -> str:
    return hashlib.sha256(external_key.encode()).hexdigest()[:16] + "@planz"


def build_event_ics(events: list, cal_name: str = "Munich Events") -> bytes:
    """Generate ICS bytes from a list of event objects.

    Events can be Event dataclasses or any object with the expected attributes.
    Uses TRANSP:OPAQUE (events block time, unlike weather which is TRANSPARENT).
    """
    cal = Calendar()
    cal.add("prodid", "-//PLANZ//planz//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("X-WR-CALNAME", cal_name)
    cal.add("REFRESH-INTERVAL;VALUE=DURATION", "PT6H")
    cal.add("X-PUBLISHED-TTL", "PT6H")

    now = datetime.now(timezone.utc)

    for ev in events:
        ical_event = Event()

        key = getattr(ev, "external_key", None) or getattr(ev, "id", "")
        ical_event.add("uid", _event_uid(key))
        ical_event.add("summary", ev.title)
        ical_event.add("dtstart", datetime.fromisoformat(ev.start_time))
        ical_event.add("dtend", datetime.fromisoformat(ev.end_time))
        ical_event.add("dtstamp", now)
        ical_event.add("transp", "OPAQUE")

        if getattr(ev, "location", None):
            ical_event.add("location", ev.location)
        if getattr(ev, "description", None):
            ical_event.add("description", ev.description)
        if getattr(ev, "source_url", None):
            ical_event.add("url", ev.source_url)

        cal.add_component(ical_event)

    return cal.to_ical()
