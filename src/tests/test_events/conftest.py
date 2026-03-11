"""Shared test fixtures for event tests."""

from types import SimpleNamespace

import pytest

from src.tests.conftest import future_iso


@pytest.fixture
def make_event_dict():
    """Factory fixture: create event dict for store_events()."""
    def _make(**overrides):
        defaults = dict(
            title="Test Event",
            start_time=future_iso(7),
            end_time=future_iso(7),
            location="Munich",
            description="A test event",
            source_url="https://example.com/event",
            category="concert",
            is_paid=False,
        )
        defaults.update(overrides)
        return defaults
    return _make


@pytest.fixture
def make_event():
    """Factory fixture: create SimpleNamespace event object for ICS tests."""
    def _make(**overrides):
        defaults = dict(
            id="test-uuid-1",
            title="Open Air Concert",
            start_time="2026-03-15T18:00:00+01:00",
            end_time="2026-03-15T21:00:00+01:00",
            location="Olympiapark, Munich",
            description="Free concert in the park",
            source_url="https://example.com/concert",
            external_key="abc123def456",
            category="concert",
            is_paid=False,
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)
    return _make
