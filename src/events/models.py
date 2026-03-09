from dataclasses import dataclass
from typing import Optional


@dataclass
class Event:
    """One calendar occurrence of a discovered event."""

    id: str  # UUID as string
    title: str
    start_time: str  # ISO 8601 datetime (timezone-aware)
    end_time: str  # ISO 8601 datetime (timezone-aware)
    location: Optional[str] = None
    description: Optional[str] = None
    source_url: Optional[str] = None
    external_key: Optional[str] = None  # SHA-256 of source_url + start_time
    category: Optional[str] = None  # one of EVENT_CATEGORIES
    is_paid: bool = False
    is_calendar_candidate: bool = True
    created_at: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            from datetime import datetime

            self.created_at = datetime.now().isoformat()


@dataclass
class EventSeries:
    """Caches detail page summaries to avoid redundant LLM calls."""

    id: str  # UUID as string
    series_key: str  # typically the detail page URL
    detail_url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    venue_address: Optional[str] = None
    category: Optional[str] = None
    is_paid: bool = False
    updated_at: Optional[str] = None

    def __post_init__(self):
        if self.updated_at is None:
            from datetime import datetime

            self.updated_at = datetime.now().isoformat()
