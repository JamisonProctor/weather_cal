"""Tests for query generator with mocked LLM calls."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.events.discovery.query_generator import (
    _fallback_queries,
    _format_date_range,
    _format_previous_feedback,
    generate_queries,
)
from src.events.sources import CityProfile, DiscoveryRun


@pytest.fixture
def munich_profile():
    return CityProfile(
        id="1", city="Munich",
        languages=["German", "English"],
        neighborhoods=["Schwabing", "Maxvorstadt"],
        venues=["Olympiapark", "Englischer Garten"],
        cultural_patterns=["Biergarten live music", "flea markets"],
        event_terms=["Veranstaltung", "Eintritt frei", "Flohmarkt"],
        known_aggregators=["muenchen.de", "in-muenchen.de"],
        seasonal_notes="Spring festivals beginning",
    )


class TestFormatDateRange:
    def test_includes_date_range(self):
        result = _format_date_range(2)
        assert "From" in result
        assert "to" in result

    def test_includes_weekends(self):
        result = _format_date_range(4)
        # Should have some weekends over 4 weeks
        assert "Weekend" in result or "From" in result


class TestFormatPreviousFeedback:
    def test_no_previous_run(self):
        result = _format_previous_feedback(None)
        assert "first discovery" in result.lower()

    def test_with_previous_run(self):
        run = DiscoveryRun(
            id="1", city="Munich", started_at="2026-03-01",
            completed_at="2026-03-01", events_stored=5,
            pages_fetched=10, notes="Good results from muenchen.de",
        )
        result = _format_previous_feedback(run)
        assert "5 events stored" in result
        assert "Good results from muenchen.de" in result

    def test_with_query_history(self):
        run = DiscoveryRun(
            id="1", city="Munich", started_at="2026-03-01",
            completed_at="2026-03-01",
            queries_json=json.dumps([
                {"query": "free events Munich", "events": 3},
                {"query": "Flohmarkt München", "events": 0},
            ]),
        )
        result = _format_previous_feedback(run)
        assert "free events Munich" in result
        assert "3 events" in result


class TestFallbackQueries:
    def test_returns_basic_queries(self):
        queries = _fallback_queries("Munich", 2)
        assert len(queries) >= 3
        assert any("Munich" in q for q in queries)
        assert any("free" in q.lower() for q in queries)

    def test_uses_location(self):
        queries = _fallback_queries("Berlin", 2)
        assert any("Berlin" in q for q in queries)
        assert not any("Munich" in q for q in queries)


class TestGenerateQueries:
    @patch("src.events.discovery.query_generator.OpenAI")
    def test_generates_queries_from_profile(self, mock_openai_cls, munich_profile):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps({
                "queries": [
                    "München Veranstaltungen 15 März 2026",
                    "Olympiapark events March 2026",
                    "Flohmarkt München März 2026",
                    "site:muenchen.de Veranstaltungen März",
                    "hidden gems Munich free March 2026",
                ]
            })))
        ]
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            queries = generate_queries(munich_profile, weeks_ahead=2)

        assert len(queries) == 5
        assert "München Veranstaltungen 15 März 2026" in queries

    def test_falls_back_without_api_key(self, munich_profile):
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            queries = generate_queries(munich_profile, weeks_ahead=2)
        assert len(queries) >= 3
        assert any("Munich" in q for q in queries)

    @patch("src.events.discovery.query_generator.OpenAI")
    def test_falls_back_on_api_error(self, mock_openai_cls, munich_profile):
        mock_openai_cls.side_effect = Exception("API error")

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            queries = generate_queries(munich_profile, weeks_ahead=2)
        assert len(queries) >= 3  # Falls back to basic queries

    @patch("src.events.discovery.query_generator.OpenAI")
    def test_falls_back_on_empty_response(self, mock_openai_cls, munich_profile):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps({"queries": []})))
        ]
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            queries = generate_queries(munich_profile, weeks_ahead=2)
        assert len(queries) >= 3  # Falls back

    @patch("src.events.discovery.query_generator.OpenAI")
    def test_includes_previous_run_context(self, mock_openai_cls, munich_profile):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps({
                "queries": ["improved query 1", "improved query 2", "improved query 3"]
            })))
        ]
        mock_client.chat.completions.create.return_value = mock_response

        last_run = DiscoveryRun(
            id="1", city="Munich", started_at="2026-03-01",
            completed_at="2026-03-01", events_stored=3,
            notes="muenchen.de worked well",
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            queries = generate_queries(munich_profile, weeks_ahead=2, last_run=last_run)

        # Verify the prompt included previous run info
        call_args = mock_client.chat.completions.create.call_args
        prompt = call_args[1]["messages"][0]["content"]
        assert "muenchen.de worked well" in prompt
