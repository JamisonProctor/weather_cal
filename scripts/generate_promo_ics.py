"""Generate static promo ICS files for iPhone screenshot demos.

Outputs:
  src/web/static/promo/weather.ics  — fake WeatherCal events (matches real format)
  src/web/static/promo/life.ics     — generic life events for overlay

Designed for two screenshots:
  1. Week view with just all-day weather events → tap into one to show detail
  2. Day/week view showing rain warning overlapping lunch, life events,
     and the sunny Sunday timed event

Usage:
  python scripts/generate_promo_ics.py
"""

import hashlib
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

TZ = ZoneInfo("Europe/Berlin")
LOCATION = "Munich, Germany"
SETTINGS_LINK = "\n\n\u2699\ufe0f Change your settings: https://weathercal.app/settings"
OUT_DIR = Path(__file__).resolve().parent.parent / "src" / "web" / "static" / "promo"


def _uid(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()[:16] + "@weathercal.app"


def _life_uid(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()[:16] + "@life-promo"


def _dt(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)


def _hourly_line(hour: int, emoji: str, temp: int, unit: str = "C",
                 precip_mm: float = 0, rain_pct: int = 0, wind: int = 0) -> str:
    parts = [f"{hour:02d}:00 {emoji} {temp}\u00b0{unit}"]
    if precip_mm > 0:
        parts.append(f"\U0001f4a7{precip_mm:.1f}mm ({rain_pct}%)")
    if wind >= 30:
        parts.append(f"\U0001f4a8{wind}km/h")
    return "  ".join(parts)


def generate_weather_ics() -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//WeatherCal//weathercal.app//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("X-WR-CALNAME", "WeatherCal")
    cal.add("X-WR-CALDESC", "Weather forecast for Munich from WeatherCal")
    cal.add("REFRESH-INTERVAL;VALUE=DURATION", "PT12H")
    cal.add("X-PUBLISHED-TTL", "PT12H")

    now = datetime(2026, 3, 18, 6, 0, tzinfo=TZ)

    # Date window: Wed Mar 18 - Mon Mar 23 (6 days for a full week view)
    wed = date(2026, 3, 18)
    thu = date(2026, 3, 19)
    fri = date(2026, 3, 20)
    sat = date(2026, 3, 21)
    sun = date(2026, 3, 22)
    mon = date(2026, 3, 23)

    events_data = []

    # --- Wednesday: mild, partly cloudy (no drama) ---
    wed_desc = "\n".join([
        _hourly_line(6, "\u2601\ufe0f", 8),
        _hourly_line(7, "\u2601\ufe0f", 9),
        _hourly_line(8, "\u26c5", 10),
        _hourly_line(9, "\u26c5", 11),
        _hourly_line(10, "\u26c5", 12),
        _hourly_line(11, "\u26c5", 13),
        _hourly_line(12, "\u2600\ufe0f", 14),
        _hourly_line(13, "\u2600\ufe0f", 14),
        _hourly_line(14, "\u26c5", 13),
        _hourly_line(15, "\u26c5", 12),
        _hourly_line(16, "\u2601\ufe0f", 11),
        _hourly_line(17, "\u2601\ufe0f", 10),
        _hourly_line(18, "\u2601\ufe0f", 9),
    ]) + SETTINGS_LINK

    events_data.append({
        "uid": _uid(f"{wed}:{LOCATION}"),
        "summary": "AM \u26c510\u00b0/13\u00b0 \u00b7 PM \u26c511\u00b0/14\u00b0",
        "start": wed,
        "end": wed + timedelta(days=1),
        "description": wed_desc,
    })

    # --- Thursday: rainy all day (the key "rained out" day) ---
    thu_desc = "\n".join([
        _hourly_line(6, "\U0001f327\ufe0f", 10, precip_mm=0.3, rain_pct=65),
        _hourly_line(7, "\U0001f327\ufe0f", 10, precip_mm=0.5, rain_pct=72),
        _hourly_line(8, "\U0001f327\ufe0f", 11, precip_mm=0.8, rain_pct=80),
        _hourly_line(9, "\U0001f327\ufe0f", 11, precip_mm=1.0, rain_pct=85),
        _hourly_line(10, "\U0001f327\ufe0f", 12, precip_mm=0.9, rain_pct=82),
        _hourly_line(11, "\U0001f327\ufe0f", 12, precip_mm=0.7, rain_pct=78),
        _hourly_line(12, "\U0001f327\ufe0f", 13, precip_mm=0.6, rain_pct=75),
        _hourly_line(13, "\U0001f327\ufe0f", 13, precip_mm=0.5, rain_pct=70),
        _hourly_line(14, "\U0001f326\ufe0f", 12, precip_mm=0.2, rain_pct=45),
        _hourly_line(15, "\u26c5", 11),
        _hourly_line(16, "\u2601\ufe0f", 10),
        _hourly_line(17, "\u2601\ufe0f", 9),
        _hourly_line(18, "\u2601\ufe0f", 8),
    ]) + SETTINGS_LINK

    events_data.append({
        "uid": _uid(f"{thu}:{LOCATION}"),
        "summary": "\u26a0\ufe0f \u2602\ufe0f AM \U0001f327\ufe0f10\u00b0/12\u00b0 \u00b7 PM \U0001f327\ufe0f8\u00b0/13\u00b0",
        "start": thu,
        "end": thu + timedelta(days=1),
        "description": thu_desc,
    })

    # Thursday timed rain warning 09:00-14:00 (overlaps with Lunch with Sara 12:00-13:00)
    thu_rain_desc = "\n".join([
        _hourly_line(9, "\U0001f327\ufe0f", 11, precip_mm=1.0, rain_pct=85),
        _hourly_line(10, "\U0001f327\ufe0f", 12, precip_mm=0.9, rain_pct=82),
        _hourly_line(11, "\U0001f327\ufe0f", 12, precip_mm=0.7, rain_pct=78),
        _hourly_line(12, "\U0001f327\ufe0f", 13, precip_mm=0.6, rain_pct=75),
        _hourly_line(13, "\U0001f327\ufe0f", 13, precip_mm=0.5, rain_pct=70),
        "",
        "High: 13\u00b0C | Low: 11\u00b0C",
    ]) + SETTINGS_LINK

    events_data.append({
        "uid": _uid(f"2026-03-19T09:00:00:{LOCATION}:rain"),
        "summary": "\u2602\ufe0f 4.2mm",
        "start": _dt(thu, 9, 0),
        "end": _dt(thu, 14, 0),
        "description": thu_rain_desc,
    })

    # --- Friday: clearing up ---
    fri_desc = "\n".join([
        _hourly_line(6, "\u2601\ufe0f", 9),
        _hourly_line(7, "\u26c5", 10),
        _hourly_line(8, "\u26c5", 11),
        _hourly_line(9, "\u26c5", 13),
        _hourly_line(10, "\u26c5", 14),
        _hourly_line(11, "\u2600\ufe0f", 15),
        _hourly_line(12, "\u2600\ufe0f", 16),
        _hourly_line(13, "\u2600\ufe0f", 17),
        _hourly_line(14, "\u2600\ufe0f", 17),
        _hourly_line(15, "\u2600\ufe0f", 16),
        _hourly_line(16, "\u26c5", 15),
        _hourly_line(17, "\u26c5", 14),
        _hourly_line(18, "\u2601\ufe0f", 12),
    ]) + SETTINGS_LINK

    events_data.append({
        "uid": _uid(f"{fri}:{LOCATION}"),
        "summary": "AM \u26c511\u00b0/14\u00b0 \u00b7 PM \u2600\ufe0f14\u00b0/17\u00b0",
        "start": fri,
        "end": fri + timedelta(days=1),
        "description": fri_desc,
    })

    # --- Saturday: nice ---
    sat_desc = "\n".join([
        _hourly_line(6, "\u26c5", 12),
        _hourly_line(7, "\u26c5", 13),
        _hourly_line(8, "\u2600\ufe0f", 14),
        _hourly_line(9, "\u2600\ufe0f", 16),
        _hourly_line(10, "\u2600\ufe0f", 17),
        _hourly_line(11, "\u2600\ufe0f", 18),
        _hourly_line(12, "\u2600\ufe0f", 20),
        _hourly_line(13, "\u2600\ufe0f", 21),
        _hourly_line(14, "\u2600\ufe0f", 21),
        _hourly_line(15, "\u2600\ufe0f", 20),
        _hourly_line(16, "\u2600\ufe0f", 19),
        _hourly_line(17, "\u26c5", 17),
        _hourly_line(18, "\u26c5", 15),
    ]) + SETTINGS_LINK

    events_data.append({
        "uid": _uid(f"{sat}:{LOCATION}"),
        "summary": "AM \u2600\ufe0f14\u00b0/17\u00b0 \u00b7 PM \u2600\ufe0f17\u00b0/21\u00b0",
        "start": sat,
        "end": sat + timedelta(days=1),
        "description": sat_desc,
    })

    # --- Sunday: beautiful sunny day ---
    sun_desc = "\n".join([
        _hourly_line(6, "\u2600\ufe0f", 14),
        _hourly_line(7, "\u2600\ufe0f", 15),
        _hourly_line(8, "\u2600\ufe0f", 17),
        _hourly_line(9, "\u2600\ufe0f", 19),
        _hourly_line(10, "\u2600\ufe0f", 21),
        _hourly_line(11, "\u2600\ufe0f", 22),
        _hourly_line(12, "\u2600\ufe0f", 23),
        _hourly_line(13, "\u2600\ufe0f", 24),
        _hourly_line(14, "\u2600\ufe0f", 25),
        _hourly_line(15, "\u2600\ufe0f", 25),
        _hourly_line(16, "\u2600\ufe0f", 24),
        _hourly_line(17, "\u2600\ufe0f", 22),
        _hourly_line(18, "\u2600\ufe0f", 20),
    ]) + SETTINGS_LINK

    events_data.append({
        "uid": _uid(f"{sun}:{LOCATION}"),
        "summary": "AM \u2600\ufe0f17\u00b0/21\u00b0 \u00b7 PM \u2600\ufe0f22\u00b0/25\u00b0",
        "start": sun,
        "end": sun + timedelta(days=1),
        "description": sun_desc,
    })

    # Sunday timed sunny event 10:00-17:00
    sun_sunny_desc = "\n".join([
        _hourly_line(10, "\u2600\ufe0f", 21),
        _hourly_line(11, "\u2600\ufe0f", 22),
        _hourly_line(12, "\u2600\ufe0f", 23),
        _hourly_line(13, "\u2600\ufe0f", 24),
        _hourly_line(14, "\u2600\ufe0f", 25),
        _hourly_line(15, "\u2600\ufe0f", 25),
        _hourly_line(16, "\u2600\ufe0f", 24),
        "",
        "High: 25\u00b0C | Low: 21\u00b0C",
    ]) + SETTINGS_LINK

    events_data.append({
        "uid": _uid(f"2026-03-22T10:00:00:{LOCATION}:sunny"),
        "summary": "\u2600\ufe0f 23 ~ 25\u00b0C",
        "start": _dt(sun, 10, 0),
        "end": _dt(sun, 17, 0),
        "description": sun_sunny_desc,
    })

    # --- Monday: cooling down ---
    mon_desc = "\n".join([
        _hourly_line(6, "\u26c5", 10),
        _hourly_line(7, "\u26c5", 11),
        _hourly_line(8, "\u26c5", 12),
        _hourly_line(9, "\u26c5", 13),
        _hourly_line(10, "\u2601\ufe0f", 14),
        _hourly_line(11, "\u2601\ufe0f", 14),
        _hourly_line(12, "\u2601\ufe0f", 15),
        _hourly_line(13, "\u26c5", 15),
        _hourly_line(14, "\u26c5", 14),
        _hourly_line(15, "\u2601\ufe0f", 13),
        _hourly_line(16, "\u2601\ufe0f", 12),
        _hourly_line(17, "\u2601\ufe0f", 11),
        _hourly_line(18, "\u2601\ufe0f", 10),
    ]) + SETTINGS_LINK

    events_data.append({
        "uid": _uid(f"{mon}:{LOCATION}"),
        "summary": "AM \u26c512\u00b0/14\u00b0 \u00b7 PM \u2601\ufe0f10\u00b0/15\u00b0",
        "start": mon,
        "end": mon + timedelta(days=1),
        "description": mon_desc,
    })

    for ed in events_data:
        event = Event()
        event.add("uid", ed["uid"])
        event.add("summary", ed["summary"])
        event.add("description", ed["description"])
        event.add("location", LOCATION)
        event.add("dtstart", ed["start"])
        event.add("dtend", ed["end"])
        event.add("transp", "TRANSPARENT")
        event.add("dtstamp", now)
        cal.add_component(event)

    cal.add_missing_timezones()
    return cal.to_ical()


def generate_life_ics() -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//LifePromo//weathercal.app//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("X-WR-CALNAME", "Life Promo")
    cal.add("REFRESH-INTERVAL;VALUE=DURATION", "PT12H")
    cal.add("X-PUBLISHED-TTL", "PT12H")

    now = datetime(2026, 3, 18, 6, 0, tzinfo=TZ)

    wed = date(2026, 3, 18)
    thu = date(2026, 3, 19)
    fri = date(2026, 3, 20)
    sat = date(2026, 3, 21)
    sun = date(2026, 3, 22)
    mon = date(2026, 3, 23)

    life_events = [
        # Wednesday
        {"summary": "Team standup", "start": _dt(wed, 9, 0), "end": _dt(wed, 9, 30), "location": ""},
        {"summary": "1:1 with Maria", "start": _dt(wed, 14, 0), "end": _dt(wed, 14, 30), "location": ""},

        # Thursday — Lunch with Sara overlaps the rain warning (12:00-13:00 inside 09:00-14:00)
        {"summary": "Team standup", "start": _dt(thu, 9, 0), "end": _dt(thu, 9, 30), "location": ""},
        {"summary": "Lunch with Sara", "start": _dt(thu, 12, 0), "end": _dt(thu, 13, 0), "location": "Marienplatz"},

        # Friday
        {"summary": "Team standup", "start": _dt(fri, 9, 0), "end": _dt(fri, 9, 30), "location": ""},
        {"summary": "Dentist", "start": _dt(fri, 14, 0), "end": _dt(fri, 15, 0), "location": ""},
        {"summary": "Dinner with Tom", "start": _dt(fri, 19, 0), "end": _dt(fri, 20, 30), "location": "Augustiner Keller"},

        # Saturday
        {"summary": "Farmers market", "start": _dt(sat, 9, 30), "end": _dt(sat, 11, 0), "location": "Viktualienmarkt"},
        {"summary": "Coffee with Alex", "start": _dt(sat, 15, 0), "end": _dt(sat, 16, 0), "location": ""},

        # Sunday — empty on purpose (nice sunny day, no plans)

        # Monday
        {"summary": "Team standup", "start": _dt(mon, 9, 0), "end": _dt(mon, 9, 30), "location": ""},
        {"summary": "Sprint planning", "start": _dt(mon, 10, 0), "end": _dt(mon, 11, 0), "location": ""},
    ]

    for le in life_events:
        event = Event()
        event.add("uid", _life_uid(le["summary"] + str(le["start"])))
        event.add("summary", le["summary"])
        event.add("dtstart", le["start"])
        event.add("dtend", le["end"])
        event.add("transp", "OPAQUE")
        event.add("dtstamp", now)
        if le["location"]:
            event.add("location", le["location"])
        cal.add_component(event)

    cal.add_missing_timezones()
    return cal.to_ical()


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    weather_path = OUT_DIR / "weather.ics"
    weather_path.write_bytes(generate_weather_ics())
    print(f"Written: {weather_path}")

    life_path = OUT_DIR / "life.ics"
    life_path.write_bytes(generate_life_ics())
    print(f"Written: {life_path}")


if __name__ == "__main__":
    main()
