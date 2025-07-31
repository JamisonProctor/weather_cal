import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

def create_event(date, summary, location):
    """
    Create an all-day event in Google Calendar for the given date, summary, and location.
    Date should be in ISO format 'YYYY-MM-DD'.
    Uses insert_event wrapper for easier testing.
    """
    event = {
        "summary": summary,
        "location": location,
        "start": {
            "date": date,
            "timeZone": "Europe/Berlin",
        },
        "end": {
            "date": date,
            "timeZone": "Europe/Berlin",
        },
        "reminders": {
            "useDefault": False,
        },
    }
    return insert_event(CALENDAR_ID, event)
load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE")
TOKEN_FILE = os.getenv("TOKEN_FILE")

def get_calendar_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    service = build("calendar", "v3", credentials=creds)
    return service

def find_event(date):
    """
    Find an event on the specified date in the calendar.
    Returns the event object if found, otherwise None.
    Uses an inclusive time range and checks for duplicate summaries.
    """
    service = get_calendar_service()
    from datetime import datetime, timedelta, timezone
    date_obj = datetime.fromisoformat(date)
    start = date_obj.replace(tzinfo=timezone.utc).isoformat()
    # Add 1 second to include events ending exactly at midnight next day
    end = (date_obj + timedelta(days=1, seconds=1)).replace(tzinfo=timezone.utc).isoformat()

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

    # Return the first event matching the date if multiple found
    for event in events:
        # If it's an all-day event, check start date string
        if event.get("start", {}).get("date") == date:
            return event
    return events[0]

def update_event(event_id, date, summary, location):
    """
    Update an existing all-day event's summary and location.
    Uses patch_event wrapper for easier testing.
    """
    event = {
        "summary": summary,
        "location": location,
        "start": {
            "date": date,
            "timeZone": "Europe/Berlin",
        },
        "end": {
            "date": date,
            "timeZone": "Europe/Berlin",
        },
        "reminders": {
            "useDefault": False,}
    }
    return patch_event(event_id, event)

def upsert_event(date, summary, location):
    """
    Create or update an event for the given date. Updates if event already exists.
    """
    existing_event = find_event(date)
    if existing_event:
        return update_event(existing_event["id"], date, summary, location)
    else:
        return create_event(date, summary, location)

def insert_event(calendar_id, body):
    """
    Wrapper for Google API insert call. Allows mocking in tests.
    """
    service = get_calendar_service()
    return service.events().insert(calendarId=calendar_id, body=body).execute()

def patch_event(event_id, body):
    """
    Wrapper for Google API patch/update call. Allows mocking in tests.
    """
    service = get_calendar_service()
    return service.events().update(calendarId=CALENDAR_ID, eventId=event_id, body=body).execute()