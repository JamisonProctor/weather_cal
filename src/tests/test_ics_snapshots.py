"""Snapshot tests to catch silent ICS format regressions.

Run with UPDATE_SNAPSHOTS=1 to regenerate baseline files:
    UPDATE_SNAPSHOTS=1 python -m pytest src/tests/test_ics_snapshots.py
"""

import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.events.ics_events import build_event_ics
from src.integrations.ics_service import generate_ics
from src.models.forecast import Forecast

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


def _strip_volatile(ics_text: str) -> str:
    """Remove fields that change between runs (timestamps, tzdata, etc.)."""
    # Strip VTIMEZONE blocks — system tzdata varies between environments
    text = re.sub(
        r"BEGIN:VTIMEZONE.*?END:VTIMEZONE\r?\n?",
        "",
        ics_text,
        flags=re.DOTALL,
    )
    lines = []
    for line in text.splitlines():
        # Skip DTSTAMP and CREATED — they change every run
        if line.startswith("DTSTAMP:") or line.startswith("CREATED:"):
            continue
        # Normalize LAST-MODIFIED
        if line.startswith("LAST-MODIFIED:"):
            continue
        # Skip empty lines left by VTIMEZONE removal
        if not line.strip():
            continue
        lines.append(line)
    return "\n".join(lines)


def _deterministic_weather_forecasts():
    """Two forecasts with fixed data for snapshot stability."""
    return [
        Forecast(
            date="2099-06-01",
            location="Munich, Germany",
            high=25, low=14,
            summary="☀️18° → ⛅25°",
            description="Mostly sunny, pleasant day",
            times=["2099-06-01T06:00", "2099-06-01T09:00", "2099-06-01T12:00", "2099-06-01T15:00"],
            temps=[14, 18, 25, 23],
            codes=[0, 1, 1, 2],
            rain=[0, 0, 0, 5],
            precipitation=[0, 0, 0, 0],
            winds=[5, 8, 10, 8],
            timezone="Europe/Berlin",
        ),
        Forecast(
            date="2099-06-02",
            location="Munich, Germany",
            high=16, low=8,
            summary="☂️ Rainy all day",
            description="Rain expected throughout",
            times=["2099-06-02T06:00", "2099-06-02T09:00", "2099-06-02T12:00", "2099-06-02T15:00"],
            temps=[8, 10, 14, 16],
            codes=[61, 61, 63, 61],
            rain=[50, 60, 80, 55],
            precipitation=[1.0, 2.0, 4.0, 1.5],
            winds=[15, 18, 20, 15],
            timezone="Europe/Berlin",
        ),
    ]


def _deterministic_events():
    """Two events with fixed data for snapshot stability."""
    return [
        SimpleNamespace(
            id="event-uuid-1",
            title="Open Air Concert",
            start_time="2099-06-01T18:00:00+02:00",
            end_time="2099-06-01T22:00:00+02:00",
            location="Olympiapark, Munich",
            description="Free concert in the park with live bands",
            source_url="https://example.com/concert",
            external_key="snapshot-concert-key-001",
            category="concert",
            is_paid=False,
        ),
        SimpleNamespace(
            id="event-uuid-2",
            title="Flea Market Schwabing",
            start_time="2099-06-02T08:00:00+02:00",
            end_time="2099-06-02T16:00:00+02:00",
            location="Leopoldstraße, Munich",
            description="Monthly flea market with vintage goods",
            source_url="https://example.com/flea-market",
            external_key="snapshot-flea-market-key-002",
            category="market",
            is_paid=False,
        ),
    ]


def _compare_or_update(snapshot_path: Path, actual: str):
    """Compare actual output against snapshot, or update if UPDATE_SNAPSHOTS=1."""
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        snapshot_path.write_text(actual, encoding="utf-8")
        return

    if not snapshot_path.exists():
        snapshot_path.write_text(actual, encoding="utf-8")
        pytest.skip(f"Snapshot created at {snapshot_path}. Re-run to validate.")

    expected = snapshot_path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"ICS output differs from snapshot at {snapshot_path}.\n"
        f"Run with UPDATE_SNAPSHOTS=1 to update the baseline."
    )


@pytest.mark.snapshot
def test_weather_ics_matches_snapshot():
    forecasts = _deterministic_weather_forecasts()
    ics_bytes = generate_ics(forecasts, "Munich, Germany")
    actual = _strip_volatile(ics_bytes.decode("utf-8"))

    snapshot_path = SNAPSHOT_DIR / "weather_feed.ics"
    _compare_or_update(snapshot_path, actual)


@pytest.mark.snapshot
def test_event_ics_matches_snapshot():
    events = _deterministic_events()
    ics_bytes = build_event_ics(events)
    actual = _strip_volatile(ics_bytes.decode("utf-8"))

    snapshot_path = SNAPSHOT_DIR / "event_feed.ics"
    _compare_or_update(snapshot_path, actual)
