"""Test suite for Google Calendar integration."""

import pytest

def test_create_calendar_event(monkeypatch):
    from weather_cal.calendar_service import create_event

    mock_called = {}
    def mock_insert_event(calendar_id, body):
        mock_called["body"] = body
        return {"id": "12345"}
    monkeypatch.setattr("weather_cal.calendar_service.insert_event", mock_insert_event)
    monkeypatch.setattr("weather_cal.calendar_service.get_calendar_service", lambda: None)

    result = create_event("2025-08-01", "☀️15° ➡️ 🌧️22°", "Munich, Germany")
    assert result["id"] == "12345"
    assert "summary" in mock_called["body"]
    assert "location" in mock_called["body"]

def test_update_calendar_event(monkeypatch):
    """Test that update_event calls the API correctly for an existing event."""
    from weather_cal.calendar_service import update_event

    mock_called = {}
    def mock_patch_event(event_id, body):
        mock_called["body"] = body
        return {"id": event_id, "updated": True}
    monkeypatch.setattr("weather_cal.calendar_service.patch_event", mock_patch_event)
    monkeypatch.setattr("weather_cal.calendar_service.get_calendar_service", lambda: None)

    result = update_event("12345", "2025-08-01", "🌤️16° ➡️ 🌧️21°", "Munich, Germany")
    assert result["updated"] is True
    assert "summary" in mock_called["body"]
    assert "location" in mock_called["body"]

def test_no_duplicate_events(monkeypatch):
    """Test that duplicate forecasts do not create new events but update existing ones."""
    from weather_cal.calendar_service import upsert_event

    calls = []
    def mock_find_event(date):
        return {"id": "existing123", "summary": "☀️15° ➡️ 🌧️22°"}
    def mock_update_event(event_id, date, summary, location):
        calls.append("update")
        return {"id": event_id}
    def mock_create_event(date, summary, location):
        calls.append("create")
        return {"id": "new456"}

    monkeypatch.setattr("weather_cal.calendar_service.find_event", mock_find_event)
    monkeypatch.setattr("weather_cal.calendar_service.update_event", mock_update_event)
    monkeypatch.setattr("weather_cal.calendar_service.create_event", mock_create_event)

    result = upsert_event("2025-08-01", "☀️15° ➡️ 🌧️22°", "Munich, Germany")
    assert result["id"] == "existing123"
    assert "update" in calls
    assert "create" not in calls

def test_calendar_api_error_handling(monkeypatch):
    """Test that calendar functions handle API errors gracefully."""
    from weather_cal.calendar_service import create_event

    def mock_insert_event(calendar_id, body):
        raise Exception("Google API failure")

    monkeypatch.setattr("weather_cal.calendar_service.insert_event", mock_insert_event)
    monkeypatch.setattr("weather_cal.calendar_service.get_calendar_service", lambda: None)

    with pytest.raises(Exception) as exc_info:
        create_event("2025-08-01", "☀️15° ➡️ 🌧️22°", "Munich, Germany")
    assert "Google API failure" in str(exc_info.value)

def test_find_event_returns_event_and_none(monkeypatch):
    """Test find_event returns event when found and None when no events exist."""
    from weather_cal.calendar_service import find_event

    class MockService:
        def events(self):
            return self
        def list(self, **kwargs):
            return self
        def execute(self):
            return {"items": [{"id": "event123", "summary": "☀️15° ➡️ 🌧️22°"}]}
    monkeypatch.setattr("weather_cal.calendar_service.get_calendar_service", lambda: MockService())
    result = find_event("2025-08-01")
    assert result["id"] == "event123"

    class MockServiceEmpty:
        def events(self):
            return self
        def list(self, **kwargs):
            return self
        def execute(self):
            return {"items": []}
    monkeypatch.setattr("weather_cal.calendar_service.get_calendar_service", lambda: MockServiceEmpty())
    result_none = find_event("2025-08-02")
    assert result_none is None

def test_upsert_event_creates_new_when_no_existing(monkeypatch):
    """Test that upsert_event creates a new event when find_event returns None."""
    from weather_cal.calendar_service import upsert_event

    calls = []
    def mock_find_event(date):
        return None
    def mock_create_event(date, summary, location):
        calls.append("create")
        return {"id": "new999"}
    def mock_update_event(event_id, date, summary, location):
        calls.append("update")
        return {"id": event_id}

    monkeypatch.setattr("weather_cal.calendar_service.find_event", mock_find_event)
    monkeypatch.setattr("weather_cal.calendar_service.create_event", mock_create_event)
    monkeypatch.setattr("weather_cal.calendar_service.update_event", mock_update_event)

    result = upsert_event("2025-08-03", "☀️19° ➡️ 🌧️24°", "Munich, Germany")
    assert result["id"] == "new999"
    assert "create" in calls
    assert "update" not in calls