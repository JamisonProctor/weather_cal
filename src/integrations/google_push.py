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

from src.services.calendar_events import (
    CalendarEvent,
    _merged_warning_uid,
    _stable_uid,
    build_calendar_events,
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
    calendar_body = {
        "summary": "WeatherCal",
        "description": "Weather forecasts from WeatherCal",
        "timeZone": "UTC",
    }
    created = service.calendars().insert(body=calendar_body).execute()
    return created["id"]


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
        logger.warning("No calendar_id for user_id=%s, skipping push", user_id)
        return

    try:
        service = build_google_service(credentials)
    except Exception:
        logger.exception("Failed to build Google service for user_id=%s", user_id)
        return

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
        logger.debug("Inserted event uid=%s", event_body.get("iCalUID"))
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
                logger.debug("Patched existing event uid=%s (409→patch)", ical_uid)
        else:
            raise


def _cleanup_stale_events(service, calendar_id, date_str,
                          expected_allday_uids, expected_timed_uids, tz):
    """Delete events for a date whose iCalUID is not in the expected sets."""
    from datetime import date as date_type

    try:
        day = date_type.fromisoformat(date_str)
        day_start = datetime.combine(day, datetime.min.time()).replace(tzinfo=tz)
        day_end = day_start + timedelta(days=1)

        existing = service.events().list(
            calendarId=calendar_id,
            timeMin=day_start.isoformat(),
            timeMax=day_end.isoformat(),
            singleEvents=True,
            maxResults=100,
        ).execute()

        for event in existing.get("items", []):
            ical_uid = event.get("iCalUID", "")
            if not ical_uid:
                continue

            is_timed = "dateTime" in event.get("start", {})
            is_allday = "date" in event.get("start", {}) and "dateTime" not in event.get("start", {})

            should_delete = False
            if is_timed and ical_uid not in expected_timed_uids:
                should_delete = True
            elif is_allday and ical_uid not in expected_allday_uids:
                should_delete = True

            if should_delete:
                try:
                    service.events().delete(
                        calendarId=calendar_id, eventId=event["id"]
                    ).execute()
                except HttpError:
                    logger.warning("Failed to delete stale event %s", event["id"], exc_info=True)
    except HttpError:
        logger.warning("Failed to list events for cleanup on %s", date_str, exc_info=True)


def _calendar_event_to_google_body(ce: CalendarEvent, tz_name: str | None) -> dict:
    """Convert a CalendarEvent to a Google Calendar API event body."""
    from datetime import date as date_type

    body = {
        "iCalUID": ce.uid,
        "summary": ce.summary,
        "description": ce.description,
        "location": ce.location,
        "transparency": ce.transparency,
    }
    if ce.is_allday:
        body["start"] = {"date": ce.start.isoformat()}
        body["end"] = {"date": ce.end.isoformat()}
    else:
        tz_str = tz_name or "UTC"
        body["start"] = {"dateTime": ce.start.isoformat(), "timeZone": tz_str}
        body["end"] = {"dateTime": ce.end.isoformat(), "timeZone": tz_str}
    return body


def _push_forecast_events(service, calendar_id, forecast, prefs, tz, tz_name):
    show_allday = prefs.get("show_allday_events", 1) if prefs else 1
    timed_enabled = prefs.get("timed_events_enabled", 1) if prefs else 1
    logger.debug("push forecast date=%s show_allday=%s timed=%s", forecast.date, show_allday, timed_enabled)

    events = build_calendar_events(forecast, prefs)
    expected_allday_uids = {e.uid for e in events if e.is_allday}
    expected_timed_uids = {e.uid for e in events if not e.is_allday}

    # Clean up stale events for this date
    _cleanup_stale_events(service, calendar_id, forecast.date,
                          expected_allday_uids, expected_timed_uids, tz)

    # Upsert current events
    for ce in events:
        event_body = _calendar_event_to_google_body(ce, tz_name)
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
