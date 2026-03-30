# WeatherCal

**A weather forecast right in your calendar.** No app to install, no website to check — just glance at your day and know what to expect.

WeatherCal adds emoji-rich daily summaries and timed weather alerts directly to your calendar. Works with Google Calendar, Apple Calendar, Outlook, and any app that supports calendar subscriptions.

> ☁️8° → ☀️14°C

That's your morning and afternoon at a glance. Open the event for the full breakdown — morning through night, with weather and temperature for each part of your day.

---

## What you get

**Daily summaries** — An all-day event at the top of each day with the weather forecast. Choose between Simple (`☁️8° → ☀️14°C`) or AM/PM (`AM☁️8° / PM☀️14°C`) format.

**Weather alerts** — Timed calendar events that show exactly when bad weather hits. Rain from 2–5pm? You'll see it right alongside your meetings so you know to grab an umbrella.

**Warning emoji** — When rain ☂️, snow ☃️, wind 🌬️, cold 🥶, or heat 🥵 are in the forecast, warning emoji replace the weather emoji in your daily summary. At a glance, before you even open the event.

**Nice weather alerts** — Not just bad weather — get notified when it's sunny and warm. Your "go outside" signal. ☀️

**Feels-like temperature** — Shows what it actually feels like outside, adjusted for wind and humidity. Or switch to actual temperature if you prefer.

**14-day forecasts** — Powered by [Open-Meteo](https://open-meteo.com/), updated multiple times per day. Global coverage, free, open data.

---

## How it works

1. **Sign up** at [weathercal.app](https://weathercal.app) and set your location.
2. **Connect your calendar** — Google Calendar syncs automatically. Apple Calendar, Outlook, and others work via a calendar subscription link (ICS).
3. **Customize** — Set your temperature thresholds, choose which alerts you want, pick your preferred format. Everything is adjustable from your settings.

That's it. Your forecast shows up in your calendar alongside your existing events.

---

## Customizable settings

- Temperature unit (°C / °F)
- Temperature display (feels like / actual)
- Daily summary title format (Simple / AM/PM)
- Cold, hot, and nice weather thresholds
- Individual alert toggles (rain, snow, wind, cold, heat, nice weather)
- Warning emoji in daily summaries (per-type toggles)
- Reminder notifications

---

## Privacy

- Free to use
- Open weather data from [Open-Meteo](https://open-meteo.com/)
- EU servers
- No tracking, no ads
- Export or delete your data anytime

---

## Tech stack

- **Backend:** Python, FastAPI, SQLite
- **Calendar:** Google Calendar API (push), ICS feed generation (pull)
- **Weather:** Open-Meteo forecast and geocoding APIs
- **Auth:** Session-based with Google OAuth for calendar connection
- **Deployment:** Docker, GitHub Actions CI/CD

---

## Development

### Prerequisites

- Python 3.10+
- Google Cloud project with Calendar API enabled (for Google Calendar integration)

### Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file with required configuration:

```bash
DEFAULT_LOCATION=Munich, Germany
OPEN_METEO_URL=https://api.open-meteo.com/v1/forecast
GEOCODE_URL=https://geocoding-api.open-meteo.com/v1/search
DB_PATH=data/forecast.db
LOG_FILE=logs/weather_cal.log
LOG_LEVEL=INFO
```

For Google Calendar push integration, add OAuth credentials:

```bash
GOOGLE_CALENDAR_ID=primary
CREDENTIALS_FILE=credentials.json
TOKEN_FILE=token.json
```

### Running locally

```bash
python -m uvicorn src.web.app:app --reload --port 8000
```

Then open http://localhost:8000.

### Tests

```bash
python -m pytest src/tests/ -q --tb=short
```

Tests cover forecast formatting, calendar event generation, user preferences, web routes, and integration behaviors.

### Docker

```bash
docker compose up --build
```

---

## License

MIT License
