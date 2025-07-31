# Weather Calendar

Weather Calendar is a Python-based script that fetches a 7-day weather forecast and automatically adds (or updates) daily all-day events in your Google Calendar. Each event title includes the forecast temperatures and weather conditions with emojis for easy at-a-glance viewing.

---

## Features

- Fetches 7-day weather forecast for a specified location (default: Munich, Germany) using the Open Meteo API.
- Stores forecasts in a local SQLite database for change detection.
- Creates or updates all-day events in Google Calendar with:
  - Morning and afternoon weather emojis
  - Low and high temperatures
- Automatically updates events if the forecast changes.
- Disables alerts/notifications for weather events.
- Includes unit tests and a mocked integration test for reliable behavior.

---

## Requirements

- Python 3.10+
- A Google account with access to Google Calendar API
- Packages listed in `requirements.txt` (install with `pip install -r requirements.txt`)

---

## Setup

1. **Clone the repository:**
   ```bash
   git clone git@github.com:JamisonProctor/weather_cal.git
   cd weather_cal
   ```

2. **Create a virtual environment and activate it:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up Google API credentials:**
   - Create OAuth credentials (Desktop app) in Google Cloud Console.
   - Download the `credentials.json` file to your project root.
   - Run the script once to generate `token.json` via browser login.

5. **Environment variables (`.env`):**
   ```
   GOOGLE_CALENDAR_ID=primary
   CREDENTIALS_FILE=credentials.json
   TOKEN_FILE=token.json
   ```

---

## Usage

Run the main script:
```bash
python main.py
```

This will:
- Fetch the latest forecast
- Store it in the SQLite database
- Create or update all-day events in your Google Calendar for the next 7 days

Events will look like:
```
☀️15° ➡️ 🌧️22°
```
and are scheduled with **no alerts**.

---

## Tests

Run all tests:
```bash
pytest -v
```

Includes:
- Unit tests for forecast parsing, DB logic, and calendar operations.
- Mocked integration test for full flow verification.

---

## Future Deployment

For running this script automatically on your server:
- Set up a **Docker container** for the app.
- Schedule the script with `cron` or similar to run daily at midnight.
- Mount a volume to persist `forecast.db` and `token.json`.

---

## License

MIT License