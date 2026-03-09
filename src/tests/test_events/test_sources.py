"""Tests for source registry, city profiles, and discovery run tracking."""

import json

import pytest

from src.events.sources import (
    CityProfile,
    DiscoveryRun,
    EventSource,
    complete_discovery_run,
    create_source_tables,
    get_active_sources,
    get_city_profile,
    get_last_discovery_run,
    record_source_fetch,
    save_city_profile,
    start_discovery_run,
    upsert_event_source,
)


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_sources.db")
    create_source_tables(path)
    return path


# --- CityProfile dataclass ---


class TestCityProfile:
    def test_defaults(self):
        p = CityProfile(id="1", city="Munich")
        assert p.languages == []
        assert p.neighborhoods == []
        assert p.created_at != ""
        assert p.updated_at != ""

    def test_with_data(self):
        p = CityProfile(
            id="1", city="Munich",
            languages=["German", "English"],
            neighborhoods=["Schwabing", "Maxvorstadt"],
            venues=["Olympiapark"],
            cultural_patterns=["Biergarten live music"],
            event_terms=["Veranstaltung", "Eintritt frei"],
            known_aggregators=["muenchen.de"],
            seasonal_notes="Spring festivals",
        )
        assert "German" in p.languages
        assert "Schwabing" in p.neighborhoods


# --- EventSource dataclass ---


class TestEventSource:
    def test_domain_extraction(self):
        s = EventSource(
            id="1", city="Munich",
            url="https://muenchen.de/events", domain="",
        )
        assert s.domain == "muenchen.de"

    def test_defaults(self):
        s = EventSource(id="1", city="Munich", url="https://example.com", domain="example.com")
        assert s.is_active is True
        assert s.total_events_found == 0
        assert s.consecutive_failures == 0


# --- City Profile CRUD ---


class TestCityProfileCRUD:
    def test_save_and_load(self, db_path):
        profile = CityProfile(
            id="test-id", city="Munich",
            languages=["German", "English"],
            neighborhoods=["Schwabing"],
            venues=["Olympiapark"],
        )
        save_city_profile(db_path, profile)

        loaded = get_city_profile(db_path, "Munich")
        assert loaded is not None
        assert loaded.city == "Munich"
        assert loaded.languages == ["German", "English"]
        assert loaded.neighborhoods == ["Schwabing"]
        assert loaded.venues == ["Olympiapark"]

    def test_load_nonexistent(self, db_path):
        assert get_city_profile(db_path, "Atlantis") is None

    def test_upsert_updates_existing(self, db_path):
        profile1 = CityProfile(
            id="id1", city="Munich", languages=["German"],
        )
        save_city_profile(db_path, profile1)

        profile2 = CityProfile(
            id="id2", city="Munich", languages=["German", "English", "Bavarian"],
        )
        save_city_profile(db_path, profile2)

        loaded = get_city_profile(db_path, "Munich")
        assert loaded.languages == ["German", "English", "Bavarian"]

    def test_multiple_cities(self, db_path):
        save_city_profile(db_path, CityProfile(id="1", city="Munich"))
        save_city_profile(db_path, CityProfile(id="2", city="Berlin"))

        assert get_city_profile(db_path, "Munich") is not None
        assert get_city_profile(db_path, "Berlin") is not None


# --- Event Source CRUD ---


class TestEventSourceCRUD:
    def test_upsert_new_source(self, db_path):
        source_id = upsert_event_source(
            db_path, "Munich", "https://muenchen.de/events",
            name="Munich Events", source_type="aggregator",
        )
        assert source_id is not None

    def test_upsert_existing_updates(self, db_path):
        id1 = upsert_event_source(db_path, "Munich", "https://example.com", name="Old")
        id2 = upsert_event_source(db_path, "Munich", "https://example.com", name="New")
        assert id1 == id2  # Same source

    def test_record_source_fetch_success(self, db_path):
        upsert_event_source(db_path, "Munich", "https://example.com")
        record_source_fetch(db_path, "Munich", "https://example.com", 5)

        sources = get_active_sources(db_path, "Munich")
        assert len(sources) == 1
        assert sources[0].total_events_found == 5
        assert sources[0].last_event_count == 5
        assert sources[0].consecutive_failures == 0

    def test_record_source_fetch_failure(self, db_path):
        upsert_event_source(db_path, "Munich", "https://example.com")
        record_source_fetch(db_path, "Munich", "https://example.com", 0)

        sources = get_active_sources(db_path, "Munich", min_events=0)
        assert len(sources) == 1
        assert sources[0].consecutive_failures == 1

    def test_get_active_sources_filters_min_events(self, db_path):
        upsert_event_source(db_path, "Munich", "https://good.com")
        upsert_event_source(db_path, "Munich", "https://bad.com")
        record_source_fetch(db_path, "Munich", "https://good.com", 10)
        record_source_fetch(db_path, "Munich", "https://bad.com", 0)

        sources = get_active_sources(db_path, "Munich", min_events=1)
        assert len(sources) == 1
        assert sources[0].url == "https://good.com"

    def test_consecutive_failures_resets_on_success(self, db_path):
        upsert_event_source(db_path, "Munich", "https://example.com")
        record_source_fetch(db_path, "Munich", "https://example.com", 0)
        record_source_fetch(db_path, "Munich", "https://example.com", 0)
        record_source_fetch(db_path, "Munich", "https://example.com", 3)

        sources = get_active_sources(db_path, "Munich")
        assert sources[0].consecutive_failures == 0
        assert sources[0].total_events_found == 3

    def test_get_active_sources_excludes_too_many_failures(self, db_path):
        upsert_event_source(db_path, "Munich", "https://flaky.com")
        for _ in range(5):
            record_source_fetch(db_path, "Munich", "https://flaky.com", 0)

        sources = get_active_sources(db_path, "Munich", min_events=0)
        assert len(sources) == 0  # 5 consecutive failures = excluded


# --- Discovery Run CRUD ---


class TestDiscoveryRunCRUD:
    def test_start_and_complete_run(self, db_path):
        run_id = start_discovery_run(db_path, "Munich")
        assert run_id is not None

        complete_discovery_run(
            db_path, run_id,
            query_count=10, urls_found=20,
            pages_fetched=15, events_extracted=8,
            events_stored=5,
            queries_json='[{"query": "test", "events": 3}]',
            notes="Good run",
        )

        last = get_last_discovery_run(db_path, "Munich")
        assert last is not None
        assert last.query_count == 10
        assert last.events_stored == 5
        assert last.notes == "Good run"
        assert last.completed_at is not None

    def test_get_last_run_returns_none_when_empty(self, db_path):
        assert get_last_discovery_run(db_path, "Munich") is None

    def test_get_last_run_returns_most_recent(self, db_path):
        run1 = start_discovery_run(db_path, "Munich")
        complete_discovery_run(db_path, run1, events_stored=3, notes="first")

        run2 = start_discovery_run(db_path, "Munich")
        complete_discovery_run(db_path, run2, events_stored=7, notes="second")

        last = get_last_discovery_run(db_path, "Munich")
        assert last.notes == "second"
        assert last.events_stored == 7

    def test_incomplete_run_not_returned(self, db_path):
        start_discovery_run(db_path, "Munich")  # Not completed
        assert get_last_discovery_run(db_path, "Munich") is None

    def test_runs_scoped_to_city(self, db_path):
        run_id = start_discovery_run(db_path, "Berlin")
        complete_discovery_run(db_path, run_id, notes="Berlin run")

        assert get_last_discovery_run(db_path, "Munich") is None
        assert get_last_discovery_run(db_path, "Berlin") is not None
