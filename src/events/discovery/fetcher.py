import asyncio
import logging

from crawl4ai import AsyncWebCrawler

logger = logging.getLogger(__name__)


async def _fetch(url: str) -> str | None:
    """Async fetch a URL and convert to Markdown via Crawl4AI."""
    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)
            if result.success and result.markdown:
                return result.markdown
            return None
    except Exception:
        logger.warning("Failed to fetch %s", url, exc_info=True)
        return None


def fetch_page_as_markdown(url: str) -> str | None:
    """Fetch a URL and convert HTML to clean Markdown text.

    Uses Crawl4AI's AsyncWebCrawler for fetching and HTML->Markdown conversion.
    This does NOT require an LLM - it's pure HTML processing.
    Returns Markdown text, or None on failure.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(lambda: asyncio.run(_fetch(url))).result(timeout=15)
        return loop.run_until_complete(_fetch(url))
    except Exception:
        logger.warning("Failed to fetch %s", url, exc_info=True)
        return None
