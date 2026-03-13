"""Generate static promo ICS files for iPhone screenshot demos.

Outputs:
  src/web/static/promo/weather.ics  — fake WeatherCal events (matches real format)
  src/web/static/promo/life.ics     — generic life events for overlay

Screenshots align with landing page copy:
  "See rain on Thursday before you schedule that outdoor lunch.
   Spot a sunny weekend while you're planning the week ahead."

  Screenshot 1: Busy Monday day view — packed calendar + weather overlay
  Screenshot 2: Thursday rain overlapping lunch + Sunday sunny timed event

Uses the REAL formatting functions from src/services/ so output
matches production exactly.

Usage:
  python scripts/generate_promo_ics.py
"""

import hashlib
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

from src.models.forecast import Forecast
from src.services.calendar_events import build_calendar_events
from src.integrations.ics_service import generate_ics

TZ = ZoneInfo("Europe/Berlin")
LOCATION = "Munich, Germany"
SETTINGS_URL = "https://weathercal.app/settings"
OUT_DIR = Path(__file__).resolve().parent.parent / "src" / "web" / "static" / "promo"

# Open-Meteo weather codes:
# 0=Clear, 1=Mainly clear, 2=Partly cloudy, 3=Overcast
# 61=Rain, 63=Moderate rain, 80=Rain showers


def _make_hours(start_hour: int = 6, end_hour: int = 18):
    """Generate ISO time strings for a given date's hours."""
    def gen(day: date):
        return [f"{day}T{h:02d}:00" for h in range(start_hour, end_hour + 1)]
    return gen


_hours = _make_hours()


def _make_forecast(day: date, temps, codes, rain_pcts, precip_mms, winds,
                   high, low, tz="Europe/Berlin") -> Forecast:
    """Build a Forecast object from hourly data arrays (hours 06-18)."""
    times = _hours(day)
    assert len(temps) == len(times), f"Expected {len(times)} temps, got {len(temps)}"
    return Forecast(
        date=str(day),
        location=LOCATION,
        summary="",
        description="",
        high=high,
        low=low,
        temps=temps,
        codes=codes,
        times=times,
        rain=rain_pcts,
        winds=winds,
        precipitation=precip_mms,
        timezone=tz,
    )


def build_forecasts() -> list[Forecast]:
    """Build fake forecast data for Mon Mar 16 – Sun Mar 22."""

    # Monday: partly cloudy, mild (no warnings)
    mon = _make_forecast(
        date(2026, 3, 16),
        temps= [7, 8, 10, 11, 12, 13, 14, 14, 13, 12, 11, 10, 8],
        codes= [3, 3, 2,  2,  2,  2,  0,  0,  2,  2,  3,  3,  3],
        rain_pcts=  [0]*13,
        precip_mms= [0]*13,
        winds= [8, 10, 12, 12, 14, 14, 12, 10, 10, 8, 8, 6, 5],
        high=14, low=7,
    )

    # Tuesday: overcast, cool
    tue = _make_forecast(
        date(2026, 3, 17),
        temps= [6, 7, 8, 9, 10, 11, 12, 12, 11, 10, 9, 8, 7],
        codes= [3, 3, 3, 3, 2,  2,  2,  2,  3,  3,  3, 3, 3],
        rain_pcts=  [0]*13,
        precip_mms= [0]*13,
        winds= [10, 12, 14, 14, 12, 10, 10, 8, 8, 6, 6, 5, 5],
        high=12, low=6,
    )

    # Wednesday: light rain morning, clearing
    wed = _make_forecast(
        date(2026, 3, 18),
        temps= [8, 8, 9, 10, 12, 13, 14, 14, 13, 12, 11, 9, 8],
        codes= [80, 80, 2, 2, 2, 0, 0, 0, 2, 2, 2, 3, 3],
        rain_pcts=  [40, 35, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        precip_mms= [0.2, 0.1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        winds= [12, 10, 10, 8, 8, 6, 6, 5, 5, 6, 8, 8, 6],
        high=14, low=8,
    )

    # THURSDAY: RAIN (the "rained out lunch" day) — rain 09-15, clearing after
    thu = _make_forecast(
        date(2026, 3, 19),
        temps= [7, 7, 8, 9, 10, 10, 11, 11, 10, 10, 9, 8, 6],
        codes= [3, 3, 3, 63, 63, 61, 61, 61, 61, 80, 3, 3, 3],
        rain_pcts=  [0, 0, 10, 85, 82, 78, 75, 70, 65, 40, 0, 0, 0],
        precip_mms= [0, 0, 0.1, 1.0, 0.9, 0.7, 0.6, 0.5, 0.5, 0.2, 0, 0, 0],
        winds= [10, 12, 14, 22, 20, 18, 16, 14, 12, 10, 8, 6, 5],
        high=11, low=6,
    )

    # Friday: clearing up, nicer
    fri = _make_forecast(
        date(2026, 3, 20),
        temps= [7, 8, 10, 12, 13, 14, 15, 16, 16, 15, 14, 12, 10],
        codes= [3, 2, 2, 2, 2, 0, 0, 0, 0, 0, 2, 2, 3],
        rain_pcts=  [0]*13,
        precip_mms= [0]*13,
        winds= [8, 8, 10, 10, 8, 6, 6, 5, 5, 6, 8, 8, 6],
        high=16, low=7,
    )

    # Saturday: warm and sunny
    sat = _make_forecast(
        date(2026, 3, 21),
        temps= [10, 11, 13, 15, 17, 18, 19, 20, 20, 19, 18, 16, 14],
        codes= [2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 2],
        rain_pcts=  [0]*13,
        precip_mms= [0]*13,
        winds= [5, 5, 6, 6, 8, 8, 6, 6, 5, 5, 5, 4, 4],
        high=20, low=10,
    )

    # SUNDAY: BEAUTIFUL SUNNY DAY (the "spot a sunny weekend" day)
    sun = _make_forecast(
        date(2026, 3, 22),
        temps= [13, 14, 16, 18, 20, 22, 23, 24, 25, 25, 24, 22, 19],
        codes= [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        rain_pcts=  [0]*13,
        precip_mms= [0]*13,
        winds= [4, 4, 5, 5, 6, 6, 6, 5, 5, 5, 4, 4, 3],
        high=25, low=13,
    )

    return [mon, tue, wed, thu, fri, sat, sun]


def generate_weather_ics() -> bytes:
    """Use the real generate_ics function for exact production format."""
    forecasts = build_forecasts()
    # Default prefs (no user customization) with sunny warnings enabled
    # so Sunday gets a timed sunny event
    prefs = {
        "temp_unit": "C",
        "show_allday_events": 1,
        "timed_events_enabled": 1,
        "warn_rain": 1,
        "warn_wind": 1,
        "warn_cold": 1,
        "warn_snow": 1,
        "warn_sunny": 0,
        "warm_threshold": 14,
        "allday_rain": 1,
        "allday_wind": 1,
        "allday_cold": 1,
        "allday_snow": 1,
        "allday_sunny": 0,
        "warn_in_allday": 1,
    }
    return generate_ics(forecasts, LOCATION, prefs=prefs, settings_url=SETTINGS_URL)


def _life_uid(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()[:16] + "@life-promo"


def _dt(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)


def generate_life_ics() -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//LifePromo//weathercal.app//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("X-WR-CALNAME", "Life Promo")
    cal.add("REFRESH-INTERVAL;VALUE=DURATION", "PT12H")
    cal.add("X-PUBLISHED-TTL", "PT12H")

    now = datetime(2026, 3, 15, 6, 0, tzinfo=TZ)

    mon = date(2026, 3, 16)
    tue = date(2026, 3, 17)
    wed = date(2026, 3, 18)
    thu = date(2026, 3, 19)
    fri = date(2026, 3, 20)
    sat = date(2026, 3, 21)

    life_events = [
        # Monday — PACKED (screenshot 1: busy person's real day)
        {"summary": "Team standup", "start": _dt(mon, 9, 0), "end": _dt(mon, 9, 30)},
        {"summary": "Design review", "start": _dt(mon, 10, 0), "end": _dt(mon, 11, 0)},
        {"summary": "Lunch", "start": _dt(mon, 12, 0), "end": _dt(mon, 12, 45)},
        {"summary": "1:1 with Maria", "start": _dt(mon, 13, 0), "end": _dt(mon, 13, 30)},
        {"summary": "Product sync", "start": _dt(mon, 14, 0), "end": _dt(mon, 15, 0)},
        {"summary": "Focus time", "start": _dt(mon, 15, 30), "end": _dt(mon, 17, 0)},
        {"summary": "Gym", "start": _dt(mon, 18, 0), "end": _dt(mon, 19, 0)},

        # Tuesday
        {"summary": "Team standup", "start": _dt(tue, 9, 0), "end": _dt(tue, 9, 30)},
        {"summary": "Sprint planning", "start": _dt(tue, 10, 0), "end": _dt(tue, 11, 30)},
        {"summary": "Dentist", "start": _dt(tue, 15, 0), "end": _dt(tue, 16, 0)},

        # Wednesday
        {"summary": "Team standup", "start": _dt(wed, 9, 0), "end": _dt(wed, 9, 30)},
        {"summary": "Backlog grooming", "start": _dt(wed, 11, 0), "end": _dt(wed, 12, 0)},
        {"summary": "Coffee with Alex", "start": _dt(wed, 15, 30), "end": _dt(wed, 16, 30)},

        # Thursday — Lunch with Sara overlaps rain warning
        {"summary": "Team standup", "start": _dt(thu, 9, 0), "end": _dt(thu, 9, 30)},
        {"summary": "Lunch with Sara", "start": _dt(thu, 12, 0), "end": _dt(thu, 13, 0)},
        {"summary": "Retro", "start": _dt(thu, 14, 0), "end": _dt(thu, 15, 0)},

        # Friday
        {"summary": "Team standup", "start": _dt(fri, 9, 0), "end": _dt(fri, 9, 30)},
        {"summary": "Demo", "start": _dt(fri, 11, 0), "end": _dt(fri, 12, 0)},
        {"summary": "Dinner with Tom", "start": _dt(fri, 19, 0), "end": _dt(fri, 20, 30)},

        # Saturday
        {"summary": "Farmers market", "start": _dt(sat, 9, 30), "end": _dt(sat, 11, 0)},

        # Sunday — empty (nice sunny day, enjoy it)
    ]

    for le in life_events:
        event = Event()
        event.add("uid", _life_uid(le["summary"] + str(le["start"])))
        event.add("summary", le["summary"])
        event.add("dtstart", le["start"])
        event.add("dtend", le["end"])
        event.add("transp", "OPAQUE")
        event.add("dtstamp", now)
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
