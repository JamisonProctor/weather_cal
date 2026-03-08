import logging

import httpx
from markdownify import markdownify

logger = logging.getLogger(__name__)

TIMEOUT = 15.0
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PlanzBot/1.0; +https://getpla.nz)",
}


def fetch_page_as_markdown(url: str) -> str | None:
    """Fetch a URL and convert HTML to clean Markdown text.

    Uses httpx for fetching and markdownify for HTML-to-Markdown conversion.
    Returns Markdown text, or None on failure.
    Timeout: 15 seconds.
    """
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        markdown = markdownify(resp.text, strip=["img", "script", "style"])
        if not markdown or not markdown.strip():
            return None
        return markdown.strip()
    except Exception:
        logger.warning("Failed to fetch %s", url, exc_info=True)
        return None
