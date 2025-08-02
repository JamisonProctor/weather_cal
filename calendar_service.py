import logging
logger = logging.getLogger(__name__)
CALENDAR_ID = "primary"
def find_event(date):
    logger.info(f"Searching for event on date {date}")
    try:
        service = get_calendar_service()
        # Define timezone and search window explicitly
        tz = "Europe/Berlin"
        start = f"{date}T00:00:00+02:00"
        end = f"{date}T23:59:59+02:00"

        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start,
            timeMax=end,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])
        if not events:
            return None
        for event in events:
            if event.get("start", {}).get("date") == date:
                return event
        return events[0]
    except Exception as e:
        logger.error(f"Failed to find event for date {date}: {e}", exc_info=True)
        raise

def get_calendar_service():
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file("token.json", ["https://www.googleapis.com/auth/calendar"])
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        logger.error(f"Failed to initialize Google Calendar service: {e}", exc_info=True)
        raise

def create_event(date, summary, location, description=None):
    service = get_calendar_service()
    event = {
        "summary": summary,
        "location": location,
        "description": description or "",
        "start": {"date": date},
        "end": {"date": date},
        "reminders": {"useDefault": False}
    }
    return service.events().insert(calendarId=CALENDAR_ID, body=event).execute()

def update_event(event_id, date, summary, location, description=None):
    service = get_calendar_service()
    event = {
        "summary": summary,
        "location": location,
        "description": description or "",
        "start": {"date": date},
        "end": {"date": date},
        "reminders": {"useDefault": False}
    }
    return service.events().update(calendarId=CALENDAR_ID, eventId=event_id, body=event).execute()

def upsert_event(date, summary, location, description=None):
    existing_event = find_event(date)
    if existing_event:
        return update_event(existing_event["id"], date, summary, location, description)
    else:
        return create_event(date, summary, location, description)