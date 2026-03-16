# constants.py — single source of truth for preference defaults and weather thresholds

SNOW_WARNING_CODES = {71, 73, 75, 77, 85, 86}
SUNNY_CODES = {0, 1, 2}
RAIN_MM_THRESHOLD = 0.5
WIND_SPEED_THRESHOLD = 30
COLD_TEMP_THRESHOLD = 3
HOT_TEMP_THRESHOLD = 28
WARM_TEMP_THRESHOLD = 14
MIN_SUNNY_HOURS = 2

DEFAULT_PREFS = {
    "cold_threshold": 3.0,
    "warn_in_allday": 1,
    "warn_rain": 1,
    "warn_wind": 1,
    "warn_cold": 1,
    "warn_snow": 1,
    "warn_sunny": 1,
    "warn_hot": 1,
    "show_allday_events": 1,
    "timed_events_enabled": 1,
    "allday_rain": 1,
    "allday_wind": 1,
    "allday_cold": 1,
    "allday_snow": 1,
    "allday_sunny": 0,
    "allday_hot": 1,
    "warm_threshold": 14.0,
    "hot_threshold": 28.0,
    "temp_unit": "C",
    "reminder_allday_hour": -1,
    "reminder_timed_minutes": -1,
}
