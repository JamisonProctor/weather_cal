import hashlib
import logging
import os
from datetime import datetime

from src.events.discovery.extractor import assess_event_quality, extract_events_from_text
from src.events.discovery.fetcher import fetch_page_as_markdown
from src.events.discovery.search import search_free_events
from src.events.store import store_events

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "data/forecast.db")


def _dedup_key(event: dict) -> str:
    raw = f"{event.get('source_url', '')}|{event.get('start_time', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()


def discover_events(location: str = "Munich", weeks_ahead: int = 2, db_path: str | None = None) -> dict:
    """Run the full discovery pipeline.

    1. Search for event pages via DuckDuckGo
    2. Fetch pages as Markdown
    3. Extract structured events via LLM
    4. Filter and deduplicate
    5. Assess quality
    6. Store to SQLite
    """
    if db_path is None:
        db_path = DB_PATH

    stats = {
        "urls_found": 0,
        "pages_fetched": 0,
        "events_extracted": 0,
        "events_quality_passed": 0,
        "store_result": None,
    }

    # Step 1: Search
    urls = search_free_events(location, weeks_ahead)
    stats["urls_found"] = len(urls)
    logger.info("Found %d URLs for %s", len(urls), location)

    if not urls:
        return stats

    # Step 2: Fetch pages
    all_events = []
    for url in urls[:20]:  # Limit to top 20 pages
        try:
            markdown = fetch_page_as_markdown(url)
            if not markdown:
                continue
            stats["pages_fetched"] += 1

            # Step 3: Extract events
            extracted = extract_events_from_text(markdown, url)
            all_events.extend(extracted)
        except Exception:
            logger.warning("Failed to process URL: %s", url, exc_info=True)
            continue

    stats["events_extracted"] = len(all_events)
    logger.info("Extracted %d events from %d pages", len(all_events), stats["pages_fetched"])

    if not all_events:
        return stats

    # Step 4: Deduplicate by source_url + start_time
    seen_keys = set()
    unique_events = []
    for event in all_events:
        key = _dedup_key(event)
        if key not in seen_keys:
            seen_keys.add(key)
            unique_events.append(event)

    # Step 5: Quality assessment
    quality_events = []
    for event in unique_events:
        try:
            if assess_event_quality(event):
                quality_events.append(event)
                stats["events_quality_passed"] += 1
        except Exception:
            logger.warning("Quality check failed for: %s", event.get("title"), exc_info=True)
            continue

    logger.info("%d events passed quality check", stats["events_quality_passed"])

    if not quality_events:
        return stats

    # Step 6: Store
    now = datetime.now()
    result = store_events(db_path, quality_events, now)
    stats["store_result"] = result
    logger.info("Store result: %s", result)

    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = discover_events()
    print(f"Discovery complete: {result}")
