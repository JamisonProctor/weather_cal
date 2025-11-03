# Weather Calendar

Weather Calendar keeps a rolling 14-day weather forecast synced to Google Calendar. Forecasts are fetched from Open-Meteo, stored in SQLite for change tracking, and rendered as all-day calendar events that stay up to date without duplicate clutter.

---

## Features

- Pulls 14-day forecasts per location using Open-Meteo forecast & geocode APIs.
- Persists each day’s data in SQLite for diff-aware updates and easy auditing.
- Builds emoji-rich summaries plus detailed descriptions for Google Calendar events.
- De-duplicates calendar entries and disables reminders to avoid notification noise.
- Runs on a scheduler (midnight by default) with logging and multi-location hooks.
- Ships with pytest coverage over services and integrations to guard regressions.

---

## Architecture at a Glance

- `src/app/main.py` — scheduler entry point; orchestrates fetch → store → calendar updates.
- `src/services/` — weather fetching, formatting, and persistence (`ForecastStore`).
- `src/integrations/calendar_service.py` — Google Calendar wrapper with duplicate cleanup.
- `src/models/forecast.py` — dataclass shared across services and integrations.
- `src/utils/` — logging config and location management helpers.
- `data/forecast.db` (or `DB_PATH`) — SQLite persistence layer for forecasts.
- `logs/` — default log destination when `LOG_FILE=logs/weather_cal.log` is set.

---

## Prerequisites

- Python 3.10+
- Google Cloud project with Calendar API enabled
- OAuth client credentials (Desktop application) for Calendar access

All required Python packages are listed in `requirements.txt`.

---

## Setup

Run these commands from the repository root:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Google API credentials

1. Create OAuth client credentials (Desktop app) in Google Cloud Console.
2. Save the downloaded `credentials.json` to the project root.
3. First-time execution will launch a browser flow and produce `token.json`. Keep both files out of source control.

### Environment configuration

Create a `.env` file (the project uses `python-dotenv`) and populate required values:

```bash
DEFAULT_LOCATION=Munich, Germany
OPEN_METEO_URL=https://api.open-meteo.com/v1/forecast
GEOCODE_URL=https://geocoding-api.open-meteo.com/v1/search
GOOGLE_CALENDAR_ID=primary
CREDENTIALS_FILE=credentials.json
TOKEN_FILE=token.json
DB_PATH=data/forecast.db
LOG_FILE=logs/weather_cal.log
LOG_LEVEL=INFO
```

- `DEFAULT_LOCATION` is used unless `load_locations_from_db()` returns records.
- `DB_PATH` and `LOG_FILE` directories are created on demand; adjust if you prefer different paths.
- Keep `.env`, `credentials.json`, and `token.json` out of version control.

---

## Running Locally

Activate your virtual environment, ensure the `.env` is loaded, then start the scheduler:

```bash
python -m src.app.main
```

By default the scheduler runs `main()` daily at midnight. For rapid iteration you can temporarily switch the interval in `schedule_jobs()` to run every minute (see the inline comment).

### Run once for an immediate sync

If you just need a single fetch/update cycle without the long-running scheduler:

```bash
python -c "from src.app.main import main; main()"
```

Each run will:
- Fetch forecasts for configured locations.
- Upsert records in SQLite for change tracking.
- Push Google Calendar events (one all-day event per location/day) with summaries and descriptions.

Logs are emitted to both stdout and the file pointed to `LOG_FILE`.

---

## Data & Logs

- Forecast data persists in SQLite at the path defined by `DB_PATH` (default `data/forecast.db`).
- Log rotation is handled by `RotatingFileHandler`; keep an eye on available disk when running over long periods.
- The scheduler and services assume directories for `DB_PATH` and `LOG_FILE` exist or can be created.

---

## Tests

Run the full pytest suite:

```bash
pytest -v
```

Tests live in `src/tests/` and cover forecast formatting, persistence, and calendar integration behaviors. Add new cases alongside the service under test.

---

## Docker (optional)

Containerized execution is available via Docker Compose:

```bash
docker compose up --build
```

Mount host volumes for `data/`, `logs/`, and OAuth tokens (`credentials.json`, `token.json`) so credentials stay local and forecast history persists between runs.

---

## Operational Tips

- Ensure the machine running the scheduler has continuous network access so the Open-Meteo and Google APIs remain reachable.
- Update `DEFAULT_LOCATION` or extend `load_locations_from_db()` when you are ready to sync multiple cities.
- Periodically review `logs/weather_cal.log` for API quota errors or calendar issues, especially after credential refreshes.

---

## License

MIT License
