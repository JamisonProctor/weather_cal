"""Tests for city profiler with mocked LLM calls."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.events.discovery.city_profiler import (
    generate_city_profile,
    get_or_create_profile,
)
from src.events.sources import CityProfile, create_source_tables, get_city_profile, save_city_profile


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_profiler.db")
    create_source_tables(path)
    return path


MOCK_PROFILE_RESPONSE = {
    "languages": ["German", "English"],
    "neighborhoods": ["Schwabing", "Maxvorstadt", "Glockenbachviertel", "Haidhausen"],
    "venues": ["Olympiapark", "Englischer Garten", "Werksviertel"],
    "cultural_patterns": ["Biergarten live music", "outdoor cinema", "flea markets"],
    "event_terms": ["Veranstaltung", "Eintritt frei", "Flohmarkt", "Straßenfest"],
    "known_aggregators": ["muenchen.de", "in-muenchen.de"],
    "seasonal_notes": "Spring brings outdoor markets and Biergarten openings",
}


class TestGenerateCityProfile:
    @patch("src.events.discovery.city_profiler.OpenAI")
    def test_generates_profile(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=json.dumps(MOCK_PROFILE_RESPONSE)))
        ]
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = generate_city_profile("Munich", "March", "2026")

        assert result["languages"] == ["German", "English"]
        assert "Schwabing" in result["neighborhoods"]
        assert "Olympiapark" in result["venues"]

    def test_no_api_key_returns_empty(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            result = generate_city_profile("Munich")
        assert result == {}

    @patch("src.events.discovery.city_profiler.OpenAI")
    def test_handles_invalid_json(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="not json"))
        ]
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = generate_city_profile("Munich")
        assert result == {}

    @patch("src.events.discovery.city_profiler.OpenAI")
    def test_handles_api_error(self, mock_openai_cls):
        mock_openai_cls.side_effect = Exception("API error")

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = generate_city_profile("Munich")
        assert result == {}


class TestGetOrCreateProfile:
    def test_loads_existing_profile(self, db_path):
        profile = CityProfile(
            id="existing", city="Munich", languages=["German"],
        )
        save_city_profile(db_path, profile)

        result = get_or_create_profile(db_path, "Munich")
        assert result is not None
        assert result.languages == ["German"]

    @patch("src.events.discovery.city_profiler.generate_city_profile")
    def test_creates_new_profile(self, mock_generate, db_path):
        mock_generate.return_value = MOCK_PROFILE_RESPONSE

        result = get_or_create_profile(db_path, "Munich")
        assert result is not None
        assert result.city == "Munich"
        assert result.languages == ["German", "English"]

        # Verify it was saved
        loaded = get_city_profile(db_path, "Munich")
        assert loaded is not None
        assert loaded.languages == ["German", "English"]

    @patch("src.events.discovery.city_profiler.generate_city_profile")
    def test_returns_none_when_generation_fails(self, mock_generate, db_path):
        mock_generate.return_value = {}

        result = get_or_create_profile(db_path, "Munich")
        assert result is None

    def test_prefers_existing_over_generating(self, db_path):
        save_city_profile(db_path, CityProfile(
            id="cached", city="Munich", languages=["Bavarian"],
        ))

        with patch("src.events.discovery.city_profiler.generate_city_profile") as mock_gen:
            result = get_or_create_profile(db_path, "Munich")
            mock_gen.assert_not_called()
            assert result.languages == ["Bavarian"]
