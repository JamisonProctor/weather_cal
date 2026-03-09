from unittest.mock import patch, MagicMock

import pytest

from src.events.db import create_event_tables
from src.events.discovery.agent import discover_events
from src.services.forecast_store import ForecastStore


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_agent.db")
    ForecastStore(db_path=path)
    create_event_tables(path)
    return path


@patch("src.events.discovery.agent.store_events")
@patch("src.events.discovery.agent.assess_event_quality")
@patch("src.events.discovery.agent.extract_events_from_text")
@patch("src.events.discovery.agent.fetch_page_as_markdown")
@patch("src.events.discovery.agent.search_free_events")
def test_discover_events_full_pipeline(mock_search, mock_fetch, mock_extract, mock_assess, mock_store, db_path):
    mock_search.return_value = ["https://example.com/page1", "https://example.com/page2"]
    mock_fetch.return_value = "# Event Page\nConcert on March 15"
    mock_extract.return_value = [
        {"title": "Concert", "start_time": "2026-03-15T18:00:00+01:00",
         "end_time": "2026-03-15T21:00:00+01:00", "source_url": "https://example.com/page1"},
    ]
    mock_assess.return_value = True
    mock_store.return_value = {"created": 1, "updated": 0, "discarded_past": 0}

    result = discover_events("Munich", weeks_ahead=2, db_path=db_path)
    assert result["pages_fetched"] == 2
    assert result["events_extracted"] >= 1
    mock_store.assert_called_once()


@patch("src.events.discovery.agent.store_events")
@patch("src.events.discovery.agent.assess_event_quality")
@patch("src.events.discovery.agent.extract_events_from_text")
@patch("src.events.discovery.agent.fetch_page_as_markdown")
@patch("src.events.discovery.agent.search_free_events")
def test_discover_events_fetch_failure_doesnt_crash(mock_search, mock_fetch, mock_extract, mock_assess, mock_store, db_path):
    mock_search.return_value = ["https://example.com/ok", "https://example.com/fail"]
    mock_fetch.side_effect = [None, "# Page content"]
    mock_extract.return_value = [
        {"title": "Event", "start_time": "2026-03-15T18:00:00+01:00",
         "end_time": "2026-03-15T21:00:00+01:00", "source_url": "https://example.com/fail"},
    ]
    mock_assess.return_value = True
    mock_store.return_value = {"created": 1, "updated": 0, "discarded_past": 0}

    result = discover_events("Munich", weeks_ahead=2, db_path=db_path)
    assert result["pages_fetched"] == 1  # only the successful one


@patch("src.events.discovery.agent.store_events")
@patch("src.events.discovery.agent.assess_event_quality")
@patch("src.events.discovery.agent.extract_events_from_text")
@patch("src.events.discovery.agent.fetch_page_as_markdown")
@patch("src.events.discovery.agent.search_free_events")
def test_discover_events_quality_filter(mock_search, mock_fetch, mock_extract, mock_assess, mock_store, db_path):
    mock_search.return_value = ["https://example.com/page"]
    mock_fetch.return_value = "content"
    mock_extract.return_value = [
        {"title": "Good Event", "start_time": "2026-03-15T18:00:00+01:00",
         "end_time": "2026-03-15T21:00:00+01:00", "source_url": "https://example.com/page"},
        {"title": "Bad Event", "start_time": "2026-03-16T18:00:00+01:00",
         "end_time": "2026-03-16T21:00:00+01:00", "source_url": "https://example.com/page"},
    ]
    mock_assess.side_effect = [True, False]
    mock_store.return_value = {"created": 1, "updated": 0, "discarded_past": 0}

    result = discover_events("Munich", weeks_ahead=2, db_path=db_path)
    assert result["events_quality_passed"] == 1


@patch("src.events.discovery.agent.store_events")
@patch("src.events.discovery.agent.assess_event_quality")
@patch("src.events.discovery.agent.extract_events_from_text")
@patch("src.events.discovery.agent.fetch_page_as_markdown")
@patch("src.events.discovery.agent.search_free_events")
def test_discover_events_no_search_results(mock_search, mock_fetch, mock_extract, mock_assess, mock_store, db_path):
    mock_search.return_value = []

    result = discover_events("Munich", weeks_ahead=2, db_path=db_path)
    assert result["pages_fetched"] == 0
    assert result["events_extracted"] == 0
    mock_fetch.assert_not_called()
    mock_store.assert_not_called()


@patch("src.events.discovery.agent.store_events")
@patch("src.events.discovery.agent.assess_event_quality")
@patch("src.events.discovery.agent.extract_events_from_text")
@patch("src.events.discovery.agent.fetch_page_as_markdown")
@patch("src.events.discovery.agent.search_free_events")
def test_discover_events_deduplicates(mock_search, mock_fetch, mock_extract, mock_assess, mock_store, db_path):
    mock_search.return_value = ["https://example.com/page"]
    mock_fetch.return_value = "content"
    # Same event extracted twice (same source_url + start_time)
    mock_extract.return_value = [
        {"title": "Event", "start_time": "2026-03-15T18:00:00+01:00",
         "end_time": "2026-03-15T21:00:00+01:00", "source_url": "https://example.com/page"},
        {"title": "Event Duplicate", "start_time": "2026-03-15T18:00:00+01:00",
         "end_time": "2026-03-15T21:00:00+01:00", "source_url": "https://example.com/page"},
    ]
    mock_assess.return_value = True
    mock_store.return_value = {"created": 1, "updated": 0, "discarded_past": 0}

    result = discover_events("Munich", weeks_ahead=2, db_path=db_path)
    # store_events receives deduplicated list
    stored_events = mock_store.call_args[0][1]
    assert len(stored_events) == 1
