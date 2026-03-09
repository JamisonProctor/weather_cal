"""Source registry, city profiles, and discovery run tracking."""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse


@dataclass
class CityProfile:
    """LLM-generated understanding of a city for informed event discovery."""

    id: str
    city: str
    languages: list[str] = field(default_factory=list)
    neighborhoods: list[str] = field(default_factory=list)
    venues: list[str] = field(default_factory=list)
    cultural_patterns: list[str] = field(default_factory=list)
    event_terms: list[str] = field(default_factory=list)
    known_aggregators: list[str] = field(default_factory=list)
    seasonal_notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


@dataclass
class EventSource:
    """A tracked URL source that may yield events."""

    id: str
    city: str
    url: str
    domain: str
    name: Optional[str] = None
    source_type: str = "unknown"
    last_fetched: Optional[str] = None
    last_event_count: int = 0
    total_events_found: int = 0
    total_fetches: int = 0
    consecutive_failures: int = 0
    is_active: bool = True
    created_at: str = ""
    notes: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.domain:
            self.domain = urlparse(self.url).netloc


@dataclass
class DiscoveryRun:
    """Record of a single discovery pipeline execution."""

    id: str
    city: str
    started_at: str
    completed_at: Optional[str] = None
    query_count: int = 0
    urls_found: int = 0
    pages_fetched: int = 0
    events_extracted: int = 0
    events_stored: int = 0
    queries_json: Optional[str] = None
    notes: Optional[str] = None


def create_source_tables(db_path: str) -> None:
    """Create city_profiles, event_sources, and discovery_runs tables."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS city_profiles (
                id TEXT PRIMARY KEY,
                city TEXT NOT NULL UNIQUE,
                languages_json TEXT DEFAULT '[]',
                neighborhoods_json TEXT DEFAULT '[]',
                venues_json TEXT DEFAULT '[]',
                cultural_patterns_json TEXT DEFAULT '[]',
                event_terms_json TEXT DEFAULT '[]',
                known_aggregators_json TEXT DEFAULT '[]',
                seasonal_notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS event_sources (
                id TEXT PRIMARY KEY,
                city TEXT NOT NULL,
                url TEXT NOT NULL,
                domain TEXT NOT NULL,
                name TEXT,
                source_type TEXT DEFAULT 'unknown',
                last_fetched TEXT,
                last_event_count INTEGER DEFAULT 0,
                total_events_found INTEGER DEFAULT 0,
                total_fetches INTEGER DEFAULT 0,
                consecutive_failures INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                notes TEXT,
                UNIQUE(city, url)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discovery_runs (
                id TEXT PRIMARY KEY,
                city TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                query_count INTEGER DEFAULT 0,
                urls_found INTEGER DEFAULT 0,
                pages_fetched INTEGER DEFAULT 0,
                events_extracted INTEGER DEFAULT 0,
                events_stored INTEGER DEFAULT 0,
                queries_json TEXT,
                notes TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


# --- City Profile CRUD ---


def save_city_profile(db_path: str, profile: CityProfile) -> None:
    """Insert or update a city profile."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO city_profiles
               (id, city, languages_json, neighborhoods_json, venues_json,
                cultural_patterns_json, event_terms_json, known_aggregators_json,
                seasonal_notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(city) DO UPDATE SET
                languages_json=excluded.languages_json,
                neighborhoods_json=excluded.neighborhoods_json,
                venues_json=excluded.venues_json,
                cultural_patterns_json=excluded.cultural_patterns_json,
                event_terms_json=excluded.event_terms_json,
                known_aggregators_json=excluded.known_aggregators_json,
                seasonal_notes=excluded.seasonal_notes,
                updated_at=excluded.updated_at""",
            (
                profile.id,
                profile.city,
                json.dumps(profile.languages),
                json.dumps(profile.neighborhoods),
                json.dumps(profile.venues),
                json.dumps(profile.cultural_patterns),
                json.dumps(profile.event_terms),
                json.dumps(profile.known_aggregators),
                profile.seasonal_notes,
                profile.created_at,
                profile.updated_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_city_profile(db_path: str, city: str) -> Optional[CityProfile]:
    """Load a city profile by city name, or None if not found."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM city_profiles WHERE city = ?", (city,)
        ).fetchone()
        if not row:
            return None
        return CityProfile(
            id=row["id"],
            city=row["city"],
            languages=json.loads(row["languages_json"]),
            neighborhoods=json.loads(row["neighborhoods_json"]),
            venues=json.loads(row["venues_json"]),
            cultural_patterns=json.loads(row["cultural_patterns_json"]),
            event_terms=json.loads(row["event_terms_json"]),
            known_aggregators=json.loads(row["known_aggregators_json"]),
            seasonal_notes=row["seasonal_notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    finally:
        conn.close()


# --- Event Source CRUD ---


def upsert_event_source(db_path: str, city: str, url: str, **kwargs) -> str:
    """Insert or update an event source. Returns the source id."""
    domain = urlparse(url).netloc
    source_id = str(uuid.uuid4())
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        existing = conn.execute(
            "SELECT id FROM event_sources WHERE city = ? AND url = ?",
            (city, url),
        ).fetchone()
        if existing:
            source_id = existing["id"]
            updates = []
            params = []
            for key in ("name", "source_type", "notes"):
                if key in kwargs:
                    updates.append(f"{key} = ?")
                    params.append(kwargs[key])
            if updates:
                params.append(source_id)
                conn.execute(
                    f"UPDATE event_sources SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
                conn.commit()
        else:
            conn.execute(
                """INSERT INTO event_sources
                   (id, city, url, domain, name, source_type, created_at, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source_id,
                    city,
                    url,
                    domain,
                    kwargs.get("name"),
                    kwargs.get("source_type", "unknown"),
                    datetime.now().isoformat(),
                    kwargs.get("notes"),
                ),
            )
            conn.commit()
        return source_id
    finally:
        conn.close()


def record_source_fetch(
    db_path: str, city: str, url: str, event_count: int
) -> None:
    """Update source stats after fetching a URL."""
    now = datetime.now().isoformat()
    conn = sqlite3.connect(db_path)
    try:
        if event_count > 0:
            conn.execute(
                """UPDATE event_sources SET
                   last_fetched = ?, last_event_count = ?,
                   total_events_found = total_events_found + ?,
                   total_fetches = total_fetches + 1,
                   consecutive_failures = 0
                   WHERE city = ? AND url = ?""",
                (now, event_count, event_count, city, url),
            )
        else:
            conn.execute(
                """UPDATE event_sources SET
                   last_fetched = ?, last_event_count = 0,
                   total_fetches = total_fetches + 1,
                   consecutive_failures = consecutive_failures + 1
                   WHERE city = ? AND url = ?""",
                (now, city, url),
            )
        conn.commit()
    finally:
        conn.close()


def get_active_sources(db_path: str, city: str, min_events: int = 1) -> list[EventSource]:
    """Return active sources for a city that have yielded at least min_events."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT * FROM event_sources
               WHERE city = ? AND is_active = 1
                 AND total_events_found >= ?
                 AND consecutive_failures < 5
               ORDER BY total_events_found DESC""",
            (city, min_events),
        ).fetchall()
        return [
            EventSource(
                id=r["id"],
                city=r["city"],
                url=r["url"],
                domain=r["domain"],
                name=r["name"],
                source_type=r["source_type"],
                last_fetched=r["last_fetched"],
                last_event_count=r["last_event_count"],
                total_events_found=r["total_events_found"],
                total_fetches=r["total_fetches"],
                consecutive_failures=r["consecutive_failures"],
                is_active=bool(r["is_active"]),
                created_at=r["created_at"],
                notes=r["notes"],
            )
            for r in rows
        ]
    finally:
        conn.close()


# --- Discovery Run CRUD ---


def start_discovery_run(db_path: str, city: str) -> str:
    """Create a new discovery run record. Returns the run id."""
    run_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO discovery_runs (id, city, started_at)
               VALUES (?, ?, ?)""",
            (run_id, city, now),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def complete_discovery_run(db_path: str, run_id: str, **kwargs) -> None:
    """Update a discovery run with final stats."""
    now = datetime.now().isoformat()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """UPDATE discovery_runs SET
               completed_at = ?,
               query_count = ?,
               urls_found = ?,
               pages_fetched = ?,
               events_extracted = ?,
               events_stored = ?,
               queries_json = ?,
               notes = ?
               WHERE id = ?""",
            (
                now,
                kwargs.get("query_count", 0),
                kwargs.get("urls_found", 0),
                kwargs.get("pages_fetched", 0),
                kwargs.get("events_extracted", 0),
                kwargs.get("events_stored", 0),
                kwargs.get("queries_json"),
                kwargs.get("notes"),
                run_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_last_discovery_run(db_path: str, city: str) -> Optional[DiscoveryRun]:
    """Return the most recent completed discovery run for a city."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """SELECT * FROM discovery_runs
               WHERE city = ? AND completed_at IS NOT NULL
               ORDER BY completed_at DESC LIMIT 1""",
            (city,),
        ).fetchone()
        if not row:
            return None
        return DiscoveryRun(
            id=row["id"],
            city=row["city"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            query_count=row["query_count"],
            urls_found=row["urls_found"],
            pages_fetched=row["pages_fetched"],
            events_extracted=row["events_extracted"],
            events_stored=row["events_stored"],
            queries_json=row["queries_json"],
            notes=row["notes"],
        )
    finally:
        conn.close()
