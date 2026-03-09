import logging

from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)


def execute_queries(queries: list[str], max_results_per_query: int = 10) -> list[str]:
    """Execute a list of search queries via DuckDuckGo. Return unique URLs."""
    seen = set()
    urls = []

    with DDGS() as ddgs:
        for query in queries:
            try:
                results = ddgs.text(query, max_results=max_results_per_query)
                for r in results:
                    href = r.get("href", "")
                    if href and href not in seen:
                        seen.add(href)
                        urls.append(href)
            except Exception:
                logger.warning("Search failed for query: %s", query, exc_info=True)
                continue

    return urls


# Keep the old interface for backwards compatibility during transition
def search_free_events(location: str = "Munich", weeks_ahead: int = 2) -> list[str]:
    """Legacy search interface — generates basic queries and searches."""
    from datetime import datetime, timedelta

    now = datetime.now()
    month = now.strftime("%B %Y")
    queries = [
        f"free events {location} {month}",
        f"{location} things to do this weekend free",
        f"{location} concerts exhibitions events {month}",
    ]
    return execute_queries(queries)
