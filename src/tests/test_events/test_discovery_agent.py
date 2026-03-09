"""Tests for the discovery agent pipeline."""

from unittest.mock import patch, MagicMock

import pytest

from src.events.db import create_event_tables
from src.events.discovery.agent import discover_events
from src.events.sources import CityProfile, create_source_tables, save_city_profile
from src.services.forecast_store import ForecastStore


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_agent.db")
    ForecastStore(db_path=path)
    create_event_tables(path)
    return path


@pytest.fixture
def db_with_profile(db_path):
    """DB with a pre-loaded Munich city profile."""
    save_city_profile(db_path, CityProfile(
        id="test", city="Munich",
        languages=["German", "English"],
        neighborhoods=["Schwabing"],
        venues=["Olympiapark"],
        cultural_patterns=["flea markets"],
        event_terms=["Veranstaltung"],
        known_aggregators=["muenchen.de"],
    ))
    return db_path


@patch("src.events.discovery.agent.store_events")
@patch("src.events.discovery.agent.assess_event_quality")
@patch("src.events.discovery.agent.extract_events_from_text")
@patch("src.events.discovery.agent.fetch_page_as_markdown")
@patch("src.events.discovery.agent.execute_queries")
@patch("src.events.discovery.agent.generate_queries")
@patch("src.events.discovery.agent.get_or_create_profile")
def test_full_pipeline(
    mock_profile, mock_gen_queries, mock_search, mock_fetch,
    mock_extract, mock_assess, mock_store, db_path,
):
    mock_profile.return_value = CityProfile(id="1", city="Munich")
    mock_gen_queries.return_value = ["query1", "query2"]
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
    assert result["profile_loaded"] is True
    assert result["queries_generated"] == 2
    mock_store.assert_called_once()


@patch("src.events.discovery.agent.store_events")
@patch("src.events.discovery.agent.assess_event_quality")
@patch("src.events.discovery.agent.extract_events_from_text")
@patch("src.events.discovery.agent.fetch_page_as_markdown")
@patch("src.events.discovery.agent.execute_queries")
@patch("src.events.discovery.agent.generate_queries")
@patch("src.events.discovery.agent.get_or_create_profile")
def test_fetch_failure_doesnt_crash(
    mock_profile, mock_gen_queries, mock_search, mock_fetch,
    mock_extract, mock_assess, mock_store, db_path,
):
    mock_profile.return_value = CityProfile(id="1", city="Munich")
    mock_gen_queries.return_value = ["query1"]
    mock_search.return_value = ["https://example.com/ok", "https://example.com/fail"]
    mock_fetch.side_effect = [None, "# Page content"]
    mock_extract.return_value = [
        {"title": "Event", "start_time": "2026-03-15T18:00:00+01:00",
         "end_time": "2026-03-15T21:00:00+01:00", "source_url": "https://example.com/fail"},
    ]
    mock_assess.return_value = True
    mock_store.return_value = {"created": 1, "updated": 0, "discarded_past": 0}

    result = discover_events("Munich", weeks_ahead=2, db_path=db_path)
    assert result["pages_fetched"] == 1


@patch("src.events.discovery.agent.store_events")
@patch("src.events.discovery.agent.assess_event_quality")
@patch("src.events.discovery.agent.extract_events_from_text")
@patch("src.events.discovery.agent.fetch_page_as_markdown")
@patch("src.events.discovery.agent.execute_queries")
@patch("src.events.discovery.agent.generate_queries")
@patch("src.events.discovery.agent.get_or_create_profile")
def test_quality_filter(
    mock_profile, mock_gen_queries, mock_search, mock_fetch,
    mock_extract, mock_assess, mock_store, db_path,
):
    mock_profile.return_value = CityProfile(id="1", city="Munich")
    mock_gen_queries.return_value = ["query1"]
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


@patch("src.events.discovery.agent.execute_queries")
@patch("src.events.discovery.agent.generate_queries")
@patch("src.events.discovery.agent.get_or_create_profile")
def test_no_search_results(mock_profile, mock_gen_queries, mock_search, db_path):
    mock_profile.return_value = CityProfile(id="1", city="Munich")
    mock_gen_queries.return_value = ["query1"]
    mock_search.return_value = []

    result = discover_events("Munich", weeks_ahead=2, db_path=db_path)
    assert result["pages_fetched"] == 0
    assert result["events_extracted"] == 0


@patch("src.events.discovery.agent.store_events")
@patch("src.events.discovery.agent.assess_event_quality")
@patch("src.events.discovery.agent.extract_events_from_text")
@patch("src.events.discovery.agent.fetch_page_as_markdown")
@patch("src.events.discovery.agent.execute_queries")
@patch("src.events.discovery.agent.generate_queries")
@patch("src.events.discovery.agent.get_or_create_profile")
def test_deduplicates(
    mock_profile, mock_gen_queries, mock_search, mock_fetch,
    mock_extract, mock_assess, mock_store, db_path,
):
    mock_profile.return_value = CityProfile(id="1", city="Munich")
    mock_gen_queries.return_value = ["query1"]
    mock_search.return_value = ["https://example.com/page"]
    mock_fetch.return_value = "content"
    mock_extract.return_value = [
        {"title": "Event", "start_time": "2026-03-15T18:00:00+01:00",
         "end_time": "2026-03-15T21:00:00+01:00", "source_url": "https://example.com/page"},
        {"title": "Event Duplicate", "start_time": "2026-03-15T18:00:00+01:00",
         "end_time": "2026-03-15T21:00:00+01:00", "source_url": "https://example.com/page"},
    ]
    mock_assess.return_value = True
    mock_store.return_value = {"created": 1, "updated": 0, "discarded_past": 0}

    result = discover_events("Munich", weeks_ahead=2, db_path=db_path)
    stored_events = mock_store.call_args[0][1]
    assert len(stored_events) == 1


@patch("src.events.discovery.agent.execute_queries")
@patch("src.events.discovery.agent.generate_queries")
@patch("src.events.discovery.agent.get_or_create_profile")
def test_no_profile_uses_fallback(mock_profile, mock_gen_queries, mock_search, db_path):
    mock_profile.return_value = None
    mock_search.return_value = []

    result = discover_events("Munich", weeks_ahead=2, db_path=db_path)
    assert result["profile_loaded"] is False
    # Should still have generated fallback queries
    assert result["queries_generated"] >= 3
    # generate_queries should NOT have been called (fallback used directly)
    mock_gen_queries.assert_not_called()


@patch("src.events.discovery.agent.store_events")
@patch("src.events.discovery.agent.assess_event_quality")
@patch("src.events.discovery.agent.extract_events_from_text")
@patch("src.events.discovery.agent.fetch_page_as_markdown")
@patch("src.events.discovery.agent.execute_queries")
@patch("src.events.discovery.agent.generate_queries")
@patch("src.events.discovery.agent.get_or_create_profile")
def test_sources_tracked(
    mock_profile, mock_gen_queries, mock_search, mock_fetch,
    mock_extract, mock_assess, mock_store, db_path,
):
    """Verify that source stats are updated after fetching."""
    mock_profile.return_value = CityProfile(id="1", city="Munich")
    mock_gen_queries.return_value = ["query1"]
    mock_search.return_value = ["https://example.com/events"]
    mock_fetch.return_value = "content"
    mock_extract.return_value = [
        {"title": "Event", "start_time": "2026-03-15T18:00:00+01:00",
         "end_time": "2026-03-15T21:00:00+01:00", "source_url": "https://example.com/events"},
    ]
    mock_assess.return_value = True
    mock_store.return_value = {"created": 1, "updated": 0, "discarded_past": 0}

    discover_events("Munich", weeks_ahead=2, db_path=db_path)

    from src.events.sources import get_active_sources
    sources = get_active_sources(db_path, "Munich")
    assert len(sources) == 1
    assert sources[0].url == "https://example.com/events"
    assert sources[0].total_events_found == 1
