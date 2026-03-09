import logging
from datetime import datetime, timedelta

from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)


def _build_queries(location: str, weeks_ahead: int) -> list[str]:
    """Generate search queries for free events."""
    now = datetime.now()
    end = now + timedelta(weeks=weeks_ahead)
    month = now.strftime("%B %Y")
    end_month = end.strftime("%B %Y")

    queries = [
        f"free events {location} this weekend {month}",
        f"kostenlose Veranstaltungen {location} {month}",
        f"{location} free outdoor activities {month}",
        f"Eintritt frei {location} Veranstaltungen {end_month}",
        f"free things to do {location} {month}",
        f"kostenlose Kinder Veranstaltungen {location}",
    ]
    return queries


def search_free_events(location: str = "Munich", weeks_ahead: int = 2) -> list[str]:
    """Search DuckDuckGo for free event pages. Return unique URLs."""
    queries = _build_queries(location, weeks_ahead)
    seen = set()
    urls = []

    with DDGS() as ddgs:
        for query in queries:
            try:
                results = ddgs.text(query, max_results=10)
                for r in results:
                    href = r.get("href", "")
                    if href and href not in seen:
                        seen.add(href)
                        urls.append(href)
            except Exception:
                logger.warning("Search failed for query: %s", query, exc_info=True)
                continue

    return urls
