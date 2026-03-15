import logging
from datetime import datetime, time, timedelta
from typing import List
from src.utils.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

_WARNING_SUMMARIES = {
    "☂️ Rain Warning",
    "🌬️ Wind Warning",
    "🥶 Cold Warning",
    "☃️ Snow Warning",
}


class CalendarService:
    def __init__(self, calendar_id="primary"):
        self.calendar_id = calendar_id
        self.service = self.get_calendar_service()

    @staticmethod
    def get_calendar_service():
        try:
            from googleapiclient.discovery import build
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file("token.json", ["https://www.googleapis.com/auth/calendar"])
            return build("calendar", "v3", credentials=creds)
        except Exception as e:
            logger.error(f"Failed to initialize Google Calendar service: {e}", exc_info=True)
            raise

    def find_events(self, date):
        """Return all events on a given date (UTC)."""
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
            # Expand the search window so all-day events created in non-UTC calendars are included.
            window_start = datetime.combine(target_date - timedelta(days=1), time(0, 0, 0)).isoformat() + "Z"
            window_end = datetime.combine(target_date + timedelta(days=1), time(23, 59, 59)).isoformat() + "Z"
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=window_start,
                timeMax=window_end,
                timeZone="UTC",
                singleEvents=True,
                orderBy="startTime"
            ).execute()
            events = events_result.get("items", [])
            filtered_events = []
            for event in events:
                start = event.get("start", {})
                event_date = start.get("date")
                if event_date == date:
                    filtered_events.append(event)
                    continue
                start_dt = start.get("dateTime")
                if start_dt and start_dt[:10] == date:
                    filtered_events.append(event)
            return filtered_events
        except Exception as e:
            logger.error(f"Failed to list events for date {date}: {e}", exc_info=True)
            return []

    def _find_matching_event(self, forecast):
        """
        Return the primary event matching the forecast location and any duplicate events
        that should be cleaned up.
        """
        events = self.find_events(forecast.date) or []
        matching_events = [
            event for event in events
            if event.get("location") == forecast.location
        ]

        if matching_events:
            primary = matching_events[0]
            duplicates = matching_events[1:]
            return primary, duplicates

        return None, []

    def _remove_duplicates(self, duplicates):
        """Remove duplicate events from Google Calendar."""
        for event in duplicates:
            try:
                self.service.events().delete(
                    calendarId=self.calendar_id,
                    eventId=event["id"]
                ).execute()
                logger.info(
                    "Removed duplicate calendar event: id=%s summary=%s",
                    event.get("id"),
                    event.get("summary"),
                )
            except Exception as e:
                logger.error(
                    "Failed to delete duplicate event id=%s: %s",
                    event.get("id"),
                    e,
                    exc_info=True,
                )

    @staticmethod
    def _format_fetch_time(fetch_time):
        if not fetch_time:
            return None
        try:
            parsed = datetime.fromisoformat(fetch_time)
            return parsed.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return fetch_time

    @staticmethod
    def _build_reminders(reminder_minutes=None):
        """Build a Google Calendar reminders dict.

        For all-day events, *minutes* counts backward from midnight of the
        event date, so ``0`` means "at midnight" (the start of the day).
        For timed events it counts backward from the event start time.
        A value of ``None`` or negative disables reminders.
        """
        if reminder_minutes is not None and reminder_minutes >= 0:
            return {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": reminder_minutes}],
            }
        return {"useDefault": False}

    def upsert_event(self, forecast, reminder_minutes=None):
        """Insert or update a Google Calendar event based on a Forecast object.

        *reminder_minutes* – minutes before midnight to fire a popup reminder
        for the all-day event.  ``0`` = midnight, ``None``/negative = no
        reminder.
        """
        try:
            base_description = forecast.description or ""
            formatted_fetch_time = self._format_fetch_time(forecast.fetch_time)
            description_parts = []
            if base_description:
                description_parts.append(base_description)
            if formatted_fetch_time:
                description_parts.append(f"Forecast last updated: {formatted_fetch_time}")
            description = "\n\n".join(description_parts).strip()

            event_body = {
                "summary": forecast.summary,
                "location": forecast.location,
                "description": description,
                "start": {"date": forecast.date},
                "end": {"date": forecast.date},
                "reminders": self._build_reminders(reminder_minutes),
            }

            existing_event, duplicates = self._find_matching_event(forecast)
            if duplicates:
                self._remove_duplicates(duplicates)

            if existing_event:
                return self.service.events().update(
                    calendarId=self.calendar_id,
                    eventId=existing_event["id"],
                    body=event_body
                ).execute()

            return self.service.events().insert(
                calendarId=self.calendar_id,
                body=event_body
            ).execute()
        except Exception as e:
            logger.error(f"Failed to upsert event for {forecast.date}: {e}", exc_info=True)
            raise

    def sync_warning_events(self, date: str, location: str, warning_windows: List, timezone: str, reminder_minutes=None) -> None:
        """
        Replace all existing timed warning events for a given date and location with
        new events derived from warning_windows. Each WarningWindow becomes one
        non-all-day calendar event spanning its start_time to end_time.
        """
        try:
            events = self.find_events(date)
            for event in events:
                is_warning = (
                    event.get("location") == location
                    and event.get("summary") in _WARNING_SUMMARIES
                    and "dateTime" in event.get("start", {})
                )
                if is_warning:
                    try:
                        self.service.events().delete(
                            calendarId=self.calendar_id,
                            eventId=event["id"]
                        ).execute()
                        logger.info(
                            "Deleted stale warning event: id=%s summary=%s",
                            event.get("id"),
                            event.get("summary"),
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to delete warning event id=%s: %s",
                            event.get("id"),
                            e,
                            exc_info=True,
                        )

            for window in warning_windows:
                summary = f"{window.emoji} {window.label}"
                event_body = {
                    "summary": summary,
                    "location": location,
                    "start": {"dateTime": window.start_time + ":00", "timeZone": timezone},
                    "end": {"dateTime": window.end_time + ":00", "timeZone": timezone},
                    "reminders": self._build_reminders(reminder_minutes),
                }
                self.service.events().insert(
                    calendarId=self.calendar_id,
                    body=event_body
                ).execute()
                logger.info(
                    "Inserted warning event: summary=%s start=%s end=%s location=%s",
                    summary,
                    window.start_time,
                    window.end_time,
                    location,
                )
        except Exception as e:
            logger.error(
                "Failed to sync warning events for date=%s location=%s: %s",
                date,
                location,
                e,
                exc_info=True,
            )
            raise
