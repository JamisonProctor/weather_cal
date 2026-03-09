import json
from unittest.mock import MagicMock, patch

import pytest

from src.events.discovery.extractor import extract_events_from_text, assess_event_quality


def _mock_openai_response(content: str):
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("src.events.discovery.extractor.OpenAI")
def test_extract_events_returns_list(mock_openai_class):
    events_json = json.dumps({"events": [
        {
            "title": "Free Concert",
            "start_time": "2026-03-15T18:00:00+01:00",
            "end_time": "2026-03-15T21:00:00+01:00",
            "location": "Olympiapark",
            "address": "Olympiapark, Munich",
            "description": "Open air concert",
            "is_free": True,
            "category": "concert",
        }
    ]})
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response(events_json)

    result = extract_events_from_text("Some markdown about a concert", "https://example.com")
    assert len(result) == 1
    assert result[0]["title"] == "Free Concert"
    assert result[0]["category"] == "concert"


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("src.events.discovery.extractor.OpenAI")
def test_extract_events_filters_non_free(mock_openai_class):
    events_json = json.dumps({"events": [
        {
            "title": "Paid Concert",
            "start_time": "2026-03-15T18:00:00+01:00",
            "end_time": "2026-03-15T21:00:00+01:00",
            "location": "Arena",
            "address": "Arena, Munich",
            "description": "Expensive concert",
            "is_free": False,
            "category": "concert",
        }
    ]})
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response(events_json)

    result = extract_events_from_text("Paid concert text", "https://example.com")
    assert len(result) == 0


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("src.events.discovery.extractor.OpenAI")
def test_extract_events_handles_invalid_json(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response("not json")

    result = extract_events_from_text("Some text", "https://example.com")
    assert result == []


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("src.events.discovery.extractor.OpenAI")
def test_extract_events_handles_api_error(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("API error")

    result = extract_events_from_text("Some text", "https://example.com")
    assert result == []


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("src.events.discovery.extractor.OpenAI")
def test_extract_events_missing_key(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response('{"events": []}')

    result = extract_events_from_text("Some text", "https://example.com")
    assert result == []


@patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False)
def test_extract_events_no_api_key():
    result = extract_events_from_text("Some text", "https://example.com")
    assert result == []


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("src.events.discovery.extractor.OpenAI")
def test_assess_event_quality_yes(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response("yes")

    event = {"title": "Free Concert", "start_time": "2026-03-15T18:00:00+01:00"}
    assert assess_event_quality(event) is True


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("src.events.discovery.extractor.OpenAI")
def test_assess_event_quality_no(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response("no")

    event = {"title": "Generic listing", "start_time": "2026-03-15T18:00:00+01:00"}
    assert assess_event_quality(event) is False


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
@patch("src.events.discovery.extractor.OpenAI")
def test_assess_event_quality_handles_error(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("API error")

    event = {"title": "Event"}
    assert assess_event_quality(event) is False


@patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False)
def test_assess_quality_no_api_key():
    assert assess_event_quality({"title": "Event"}) is False
