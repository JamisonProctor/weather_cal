import logging
from urllib.parse import urlparse

from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

# Domains that never contain local event listings
BLOCKED_DOMAINS = {
    "support.google.com",
    "accounts.google.com",
    "play.google.com",
    "zhihu.com",
    "www.zhihu.com",
    "instagram.com",
    "www.instagram.com",
    "facebook.com",
    "www.facebook.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "www.youtube.com",
    "meta.com",
    "www.meta.com",
    "wikipedia.org",
    "de.wikipedia.org",
    "en.wikipedia.org",
    "amazon.com",
    "amazon.de",
    "reddit.com",
    "www.reddit.com",
    "pinterest.com",
    "pinterest.de",
    "tiktok.com",
    "www.tiktok.com",
    "linkedin.com",
    "www.linkedin.com",
    "spotify.com",
    "open.spotify.com",
}


def _is_relevant_url(url: str) -> bool:
    """Filter out URLs from domains that never contain event listings."""
    try:
        domain = urlparse(url).netloc.lower()
        # Check exact match and parent domain
        if domain in BLOCKED_DOMAINS:
            return False
        # Check if it's a subdomain of a blocked domain
        for blocked in BLOCKED_DOMAINS:
            if domain.endswith("." + blocked):
                return False
        return True
    except Exception:
        return False


def execute_queries(
    queries: list[str],
    max_results_per_query: int = 5,
    region: str = "de-de",
) -> list[str]:
    """Execute a list of search queries via DuckDuckGo. Return unique URLs."""
    seen = set()
    urls = []

    with DDGS() as ddgs:
        for query in queries:
            try:
                results = ddgs.text(
                    query, max_results=max_results_per_query, region=region
                )
                for r in results:
                    href = r.get("href", "")
                    if href and href not in seen and _is_relevant_url(href):
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
