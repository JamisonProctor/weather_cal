import pytest

from src.integrations.calendar_service import CalendarService
from src.models.forecast import Forecast


class FakeEventsClient:
    """Minimal fake for Google Calendar events client."""

    def __init__(self, items):
        self.items = items
        self.deleted_ids = []
        self.updated_calls = []
        self.inserted_calls = []

    class _ListCall:
        def __init__(self, items):
            self.items = items

        def execute(self):
            return {"items": self.items}

    class _DeleteCall:
        def __init__(self, outer, event_id):
            self.outer = outer
            self.event_id = event_id

        def execute(self):
            self.outer.deleted_ids.append(self.event_id)
            return {}

    class _UpdateCall:
        def __init__(self, outer, event_id, body):
            self.outer = outer
            self.event_id = event_id
            self.body = body

        def execute(self):
            self.outer.updated_calls.append((self.event_id, self.body))
            return {"id": self.event_id, **self.body}

    class _InsertCall:
        def __init__(self, outer, body):
            self.outer = outer
            self.body = body

        def execute(self):
            self.outer.inserted_calls.append(self.body)
            return {"id": "new-event-id", **self.body}

    def list(self, **_kwargs):
        return self._ListCall(self.items)

    def delete(self, calendarId, eventId):
        return self._DeleteCall(self, eventId)

    def update(self, calendarId, eventId, body):
        return self._UpdateCall(self, eventId, body)

    def insert(self, calendarId, body):
        return self._InsertCall(self, body)


class FakeService:
    def __init__(self, items):
        self.events_client = FakeEventsClient(items)

    def events(self):
        return self.events_client


def _build_forecast(date="2025-10-21", location="Munich"):
    return Forecast(
        date=date,
        location=location,
        high=20,
        low=10,
        summary="Updated forecast",
        description="Details",
        times=[],
        temps=[],
        codes=[],
        rain=[],
        winds=[],
    )


def test_upsert_event_removes_duplicates_before_update(monkeypatch):
    existing_events = [
        {"id": "primary-id", "location": "Munich", "summary": "Old"},
        {"id": "duplicate-id", "location": "Munich", "summary": "Older"},
        {"id": "other-location", "location": "Berlin", "summary": "Ignore"},
    ]
    fake_service = FakeService(existing_events)
    monkeypatch.setattr(CalendarService, "get_calendar_service", staticmethod(lambda: fake_service))

    calendar = CalendarService()
    forecast = _build_forecast()

    calendar.upsert_event(forecast)

    assert fake_service.events_client.deleted_ids == ["duplicate-id"]
    assert len(fake_service.events_client.updated_calls) == 1
    updated_id, updated_body = fake_service.events_client.updated_calls[0]
    assert updated_id == "primary-id"
    assert updated_body["summary"] == forecast.summary
    assert fake_service.events_client.inserted_calls == []


def test_upsert_event_inserts_when_no_existing_match(monkeypatch):
    existing_events = [
        {"id": "other", "location": "Berlin", "summary": "No match"},
    ]
    fake_service = FakeService(existing_events)
    monkeypatch.setattr(CalendarService, "get_calendar_service", staticmethod(lambda: fake_service))

    calendar = CalendarService()
    forecast = _build_forecast(location="Munich")

    calendar.upsert_event(forecast)

    assert fake_service.events_client.deleted_ids == []
    assert fake_service.events_client.updated_calls == []
    assert len(fake_service.events_client.inserted_calls) == 1
    inserted_body = fake_service.events_client.inserted_calls[0]
    assert inserted_body["summary"] == forecast.summary
