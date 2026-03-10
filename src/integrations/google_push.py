import hashlib
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.integrations.ics_service import (
    _merged_window_summary,
    _format_window_description,
    _stable_uid,
    _merged_warning_uid,
)
from src.services.forecast_formatting import (
    format_detailed_forecast,
    format_summary,
    get_warning_windows,
    merge_overlapping_windows,
)

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.app.created"]


def _conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_google_tokens_table(db_path: str) -> None:
    conn = _conn(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS google_tokens (
                user_id            INTEGER PRIMARY KEY REFERENCES users(id),
                access_token       TEXT NOT NULL,
                refresh_token      TEXT NOT NULL,
                token_expiry       TEXT,
                google_calendar_id TEXT,
                status             TEXT NOT NULL DEFAULT 'active',
                connected_at       TEXT NOT NULL,
                updated_at         TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def google_oauth_enabled() -> bool:
    return bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))


def get_oauth_flow(redirect_uri: str) -> Flow:
    client_config = {
        "web": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    return flow


def store_google_tokens(
    db_path: str, user_id: int, credentials: Credentials, calendar_id: str | None = None
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    token_expiry = credentials.expiry.isoformat() if credentials.expiry else None
    conn = _conn(db_path)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO google_tokens
               (user_id, access_token, refresh_token, token_expiry, google_calendar_id,
                status, connected_at, updated_at)
               VALUES (?, ?, ?, ?, ?,
                       'active',
                       COALESCE((SELECT connected_at FROM google_tokens WHERE user_id = ?), ?),
                       ?)""",
            (user_id, credentials.token, credentials.refresh_token, token_expiry,
             calendar_id, user_id, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_google_credentials(db_path: str, user_id: int) -> Credentials | None:
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM google_tokens WHERE user_id = ? AND status = 'active'",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        expiry = datetime.fromisoformat(row["token_expiry"]) if row["token_expiry"] else None
        return Credentials(
            token=row["access_token"],
            refresh_token=row["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            expiry=expiry,
        )
    finally:
        conn.close()


def refresh_and_persist(db_path: str, user_id: int, credentials: Credentials) -> Credentials | None:
    if credentials.valid:
        return credentials
    try:
        credentials.refresh(Request())
    except RefreshError:
        logger.warning("Google token refresh failed for user_id=%s, marking revoked", user_id)
        _mark_revoked(db_path, user_id)
        return None
    # Persist refreshed tokens
    now = datetime.now(timezone.utc).isoformat()
    token_expiry = credentials.expiry.isoformat() if credentials.expiry else None
    conn = _conn(db_path)
    try:
        conn.execute(
            """UPDATE google_tokens
               SET access_token = ?, refresh_token = ?, token_expiry = ?, updated_at = ?
               WHERE user_id = ?""",
            (credentials.token, credentials.refresh_token, token_expiry, now, user_id),
        )
        conn.commit()
    finally:
        conn.close()
    return credentials


def _mark_revoked(db_path: str, user_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = _conn(db_path)
    try:
        conn.execute(
            "UPDATE google_tokens SET status = 'revoked', updated_at = ? WHERE user_id = ?",
            (now, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_google_calendar(db_path: str, user_id: int) -> None:
    """Delete the WeatherCal calendar from the user's Google account."""
    credentials = get_google_credentials(db_path, user_id)
    if not credentials:
        return

    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT google_calendar_id FROM google_tokens WHERE user_id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()

    calendar_id = row["google_calendar_id"] if row else None
    if not calendar_id:
        return

    credentials = refresh_and_persist(db_path, user_id, credentials)
    if not credentials:
        return

    try:
        service = build_google_service(credentials)
        service.calendars().delete(calendarId=calendar_id).execute()
        logger.info("Deleted Google calendar %s for user_id=%s", calendar_id, user_id)
    except HttpError as e:
        if e.resp.status == 404:
            logger.info("Google calendar %s already deleted for user_id=%s", calendar_id, user_id)
        else:
            logger.warning("Failed to delete Google calendar for user_id=%s: %s", user_id, e)
    except Exception:
        logger.warning("Failed to delete Google calendar for user_id=%s", user_id, exc_info=True)


def delete_google_tokens(db_path: str, user_id: int) -> None:
    conn = _conn(db_path)
    try:
        conn.execute("DELETE FROM google_tokens WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def is_google_connected(db_path: str, user_id: int) -> bool:
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM google_tokens WHERE user_id = ? AND status = 'active'",
            (user_id,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_google_connected_users(db_path: str) -> list[dict]:
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT user_id, google_calendar_id FROM google_tokens WHERE status = 'active'"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def build_google_service(credentials: Credentials):
    return build("calendar", "v3", credentials=credentials)


def create_weathercal_calendar(service, location: str = "") -> str:
    city = location.split(",")[0].strip() if "," in location else location
    summary = f"WeatherCal \u2014 {city}" if city else "WeatherCal"
    description = f"Weather forecasts for {city} from WeatherCal" if city else "Weather forecasts from WeatherCal"
    calendar_body = {
        "summary": summary,
        "description": description,
        "timeZone": "UTC",
    }
    created = service.calendars().insert(body=calendar_body).execute()
    return created["id"]


def _expected_calendar_summary(location: str) -> str:
    city = location.split(",")[0].strip() if "," in location else location
    return f"WeatherCal \u2014 {city}" if city else "WeatherCal"


def _sync_calendar_name(service, calendar_id: str, location: str):
    """Rename the Google Calendar if the user's location has changed."""
    expected = _expected_calendar_summary(location)
    try:
        cal = service.calendars().get(calendarId=calendar_id).execute()
        if cal.get("summary") != expected:
            city = location.split(",")[0].strip() if "," in location else location
            cal["summary"] = expected
            cal["description"] = f"Weather forecasts for {city} from WeatherCal" if city else "Weather forecasts from WeatherCal"
            service.calendars().patch(calendarId=calendar_id, body={
                "summary": cal["summary"],
                "description": cal["description"],
            }).execute()
            logger.info("Renamed Google calendar %s to '%s'", calendar_id, expected)
    except HttpError:
        logger.warning("Failed to sync calendar name for %s", calendar_id, exc_info=True)


def push_events_for_user(db_path, user_id, forecasts, prefs, location, tz_name):
    credentials = get_google_credentials(db_path, user_id)
    if not credentials:
        return
    credentials = refresh_and_persist(db_path, user_id, credentials)
    if not credentials:
        return

    # Get calendar_id
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT google_calendar_id FROM google_tokens WHERE user_id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()

    calendar_id = row["google_calendar_id"] if row else None
    if not calendar_id:
        return

    try:
        service = build_google_service(credentials)
    except Exception:
        logger.exception("Failed to build Google service for user_id=%s", user_id)
        return

    # Update calendar name if location changed
    _sync_calendar_name(service, calendar_id, location)

    try:
        tz = ZoneInfo(tz_name) if tz_name else timezone.utc
    except ZoneInfoNotFoundError:
        tz = timezone.utc

    for forecast in forecasts:
        try:
            _push_forecast_events(service, calendar_id, forecast, prefs, tz, tz_name)
        except HttpError as e:
            if e.resp.status == 404:
                logger.warning("Calendar %s not found for user_id=%s, clearing calendar_id", calendar_id, user_id)
                _clear_calendar_id(db_path, user_id)
                return
            raise
        except RefreshError:
            _mark_revoked(db_path, user_id)
            return


def _upsert_event(service, calendar_id, event_body):
    """Insert an event, or patch it if it already exists (by iCalUID)."""
    try:
        service.events().import_(calendarId=calendar_id, body=event_body).execute()
    except HttpError as e:
        if e.resp.status == 409:
            # Event already exists — find it by iCalUID and patch
            ical_uid = event_body["iCalUID"]
            existing = service.events().list(
                calendarId=calendar_id, iCalUID=ical_uid, maxResults=1
            ).execute()
            items = existing.get("items", [])
            if items:
                event_id = items[0]["id"]
                patch_body = {k: v for k, v in event_body.items() if k != "iCalUID"}
                service.events().patch(
                    calendarId=calendar_id, eventId=event_id, body=patch_body
                ).execute()
        else:
            raise


def _push_forecast_events(service, calendar_id, forecast, prefs, tz, tz_name):
    from datetime import date as date_type

    show_allday = prefs.get("show_allday_events", 1) if prefs else 1
    if show_allday:
        uid = _stable_uid(forecast.date, forecast.location)
        summary = format_summary(forecast, prefs) if prefs else (forecast.summary or "Weather")
        description = format_detailed_forecast(forecast, prefs) if prefs else (forecast.description or "")

        event_body = {
            "iCalUID": uid,
            "summary": summary,
            "description": description,
            "start": {"date": forecast.date},
            "end": {"date": (date_type.fromisoformat(forecast.date) + timedelta(days=1)).isoformat()},
            "transparency": "transparent",
        }
        _upsert_event(service, calendar_id, event_body)

    timed_enabled = prefs.get("timed_events_enabled", 1) if prefs else 1
    if timed_enabled:
        windows = get_warning_windows(forecast, prefs)
        merged_windows = merge_overlapping_windows(windows)
        for merged in merged_windows:
            uid = _merged_warning_uid(merged.start_time, forecast.location, merged.warning_types)
            summary = _merged_window_summary(merged, forecast, prefs)
            description = _format_window_description(forecast, merged, prefs)
            tz_str = tz_name or "UTC"

            event_body = {
                "iCalUID": uid,
                "summary": summary,
                "description": description,
                "start": {
                    "dateTime": datetime.fromisoformat(merged.start_time).replace(tzinfo=tz).isoformat(),
                    "timeZone": tz_str,
                },
                "end": {
                    "dateTime": datetime.fromisoformat(merged.end_time).replace(tzinfo=tz).isoformat(),
                    "timeZone": tz_str,
                },
                "transparency": "transparent",
            }
            _upsert_event(service, calendar_id, event_body)


def _clear_calendar_id(db_path: str, user_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = _conn(db_path)
    try:
        conn.execute(
            "UPDATE google_tokens SET google_calendar_id = NULL, updated_at = ? WHERE user_id = ?",
            (now, user_id),
        )
        conn.commit()
    finally:
        conn.close()
