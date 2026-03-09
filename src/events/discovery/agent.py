"""Event discovery pipeline: profile → generate queries → search → extract → learn."""

import hashlib
import json
import logging
import os
from datetime import datetime

from src.events.discovery.city_profiler import get_or_create_profile
from src.events.discovery.extractor import assess_event_quality, extract_events_from_text
from src.events.discovery.fetcher import fetch_page_as_markdown
from src.events.discovery.query_generator import generate_queries
from src.events.discovery.search import execute_queries
from src.events.sources import (
    complete_discovery_run,
    get_active_sources,
    get_last_discovery_run,
    record_source_fetch,
    start_discovery_run,
    upsert_event_source,
)
from src.events.store import store_events

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "data/forecast.db")


def _dedup_key(event: dict) -> str:
    raw = f"{event.get('source_url', '')}|{event.get('start_time', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()


def discover_events(
    location: str = "Munich", weeks_ahead: int = 2, db_path: str | None = None
) -> dict:
    """Run the full intelligent discovery pipeline.

    1. Load/create city profile
    2. Generate queries from profile + date range + history
    3. Collect URLs from known sources + search results
    4. Fetch pages as Markdown
    5. Extract structured events via LLM
    6. Deduplicate and quality filter
    7. Store to SQLite
    8. Update source stats + discovery run log
    """
    if db_path is None:
        db_path = DB_PATH

    stats = {
        "urls_found": 0,
        "pages_fetched": 0,
        "events_extracted": 0,
        "events_quality_passed": 0,
        "store_result": None,
        "profile_loaded": False,
        "queries_generated": 0,
    }

    # Step 1: City profile
    profile = get_or_create_profile(db_path, location)
    if profile:
        stats["profile_loaded"] = True
    else:
        logger.warning("No city profile available for %s, using basic search", location)

    # Step 2: Generate queries
    last_run = get_last_discovery_run(db_path, location)
    if profile:
        queries = generate_queries(profile, weeks_ahead, last_run)
    else:
        from src.events.discovery.query_generator import _fallback_queries
        queries = _fallback_queries(location, weeks_ahead)
    stats["queries_generated"] = len(queries)
    logger.info("Generated %d queries for %s", len(queries), location)

    # Start tracking this run
    run_id = start_discovery_run(db_path, location)

    # Step 3: Collect URLs — known good sources + search results
    all_urls = []
    known_sources = get_active_sources(db_path, location)
    known_urls = [s.url for s in known_sources]
    all_urls.extend(known_urls)
    logger.info("Added %d known good source URLs", len(known_urls))

    search_urls = execute_queries(queries)
    for url in search_urls:
        if url not in all_urls:
            all_urls.append(url)
    stats["urls_found"] = len(all_urls)
    logger.info("Total %d unique URLs to fetch", len(all_urls))

    if not all_urls:
        complete_discovery_run(
            db_path, run_id,
            query_count=len(queries), urls_found=0,
            notes="No URLs found from search or known sources",
        )
        return stats

    # Track query results for learning
    query_results = [{"query": q, "events": 0} for q in queries]

    # Step 4-5: Fetch pages and extract events
    all_events = []
    url_event_counts = {}  # url -> count for source tracking

    for url in all_urls[:30]:  # Limit to top 30 pages
        try:
            # Register source
            upsert_event_source(db_path, location, url)

            markdown = fetch_page_as_markdown(url)
            if not markdown:
                record_source_fetch(db_path, location, url, 0)
                continue
            stats["pages_fetched"] += 1

            extracted = extract_events_from_text(markdown, url)
            url_event_counts[url] = len(extracted)
            all_events.extend(extracted)

            # Update source stats
            record_source_fetch(db_path, location, url, len(extracted))
        except Exception:
            logger.warning("Failed to process URL: %s", url, exc_info=True)
            continue

    stats["events_extracted"] = len(all_events)
    logger.info("Extracted %d events from %d pages", len(all_events), stats["pages_fetched"])

    if not all_events:
        complete_discovery_run(
            db_path, run_id,
            query_count=len(queries), urls_found=stats["urls_found"],
            pages_fetched=stats["pages_fetched"], events_extracted=0,
            queries_json=json.dumps(query_results),
            notes="No events extracted from any pages",
        )
        return stats

    # Step 6: Deduplicate by source_url + start_time
    seen_keys = set()
    unique_events = []
    for event in all_events:
        key = _dedup_key(event)
        if key not in seen_keys:
            seen_keys.add(key)
            unique_events.append(event)

    # Step 7: Quality assessment
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
        complete_discovery_run(
            db_path, run_id,
            query_count=len(queries), urls_found=stats["urls_found"],
            pages_fetched=stats["pages_fetched"],
            events_extracted=stats["events_extracted"],
            queries_json=json.dumps(query_results),
            notes=f"0 of {len(unique_events)} events passed quality check",
        )
        return stats

    # Step 8: Store
    now = datetime.now()
    result = store_events(db_path, quality_events, now)
    stats["store_result"] = result
    logger.info("Store result: %s", result)

    # Step 9: Complete discovery run log
    events_stored = result.get("created", 0) + result.get("updated", 0)
    complete_discovery_run(
        db_path, run_id,
        query_count=len(queries),
        urls_found=stats["urls_found"],
        pages_fetched=stats["pages_fetched"],
        events_extracted=stats["events_extracted"],
        events_stored=events_stored,
        queries_json=json.dumps(query_results),
        notes=f"Stored {events_stored} events ({result.get('created', 0)} new, {result.get('updated', 0)} updated)",
    )

    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from src.events.db import create_event_tables

    db = os.getenv("DB_PATH", "data/forecast.db")
    create_event_tables(db)
    result = discover_events(db_path=db)
    print(f"Discovery complete: {result}")
