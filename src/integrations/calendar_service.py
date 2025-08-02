import logging
from src.utils.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

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

    def find_event(self, date):
        """Find the first event on a given date (UTC)."""
        try:
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=f"{date}T00:00:00Z",
                timeMax=f"{date}T23:59:59Z",
                singleEvents=True,
                orderBy="startTime"
            ).execute()
            events = events_result.get("items", [])
            return events[0] if events else None
        except Exception as e:
            logger.error(f"Failed to find event for date {date}: {e}", exc_info=True)
            return None

    def upsert_event(self, forecast):
        """Insert or update a Google Calendar event based on a Forecast object."""
        try:
            event_body = {
                "summary": forecast.summary,
                "location": forecast.location,
                "description": forecast.description or "",
                "start": {"date": forecast.date},
                "end": {"date": forecast.date},
                "reminders": {"useDefault": False}
            }

            existing_event = self.find_event(forecast.date)
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