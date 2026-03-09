"""LLM-informed query generation from city profile, date range, and history."""

import json
import logging
import os
from datetime import datetime, timedelta

from openai import OpenAI

from src.events.sources import CityProfile, DiscoveryRun

logger = logging.getLogger(__name__)

QUERY_GENERATION_PROMPT = """You are generating search queries to find FREE local events in {city}.

## City Profile
- Languages: {languages}
- Neighborhoods: {neighborhoods}
- Venues: {venues}
- Cultural patterns: {cultural_patterns}
- Local event terms: {event_terms}
- Known aggregator sites: {aggregators}
- Seasonal notes: {seasonal_notes}

## Target Date Range
{date_range}

## Previous Run Feedback
{previous_feedback}

## Instructions
Generate 8-12 search queries across these strategies:
1. DATE-SPECIFIC: Search for events on specific dates (especially weekends) in local language(s). Example: "München Veranstaltungen 15 März 2026"
2. VENUE-SPECIFIC: Search for events at known venues. Example: "Olympiapark events March 2026"
3. EVENT-TYPE: Search for specific event types from cultural patterns. Example: "Flohmarkt München März 2026"
4. AGGREGATOR: Target known listing sites with site: prefix. Example: "site:muenchen.de Veranstaltungen März 2026"
5. DISCOVERY: Broader queries to find new types of events. Example: "hidden gems Munich free events March 2026"

Rules:
- Use local language(s) for at least half the queries
- Include specific dates (format: "15 März 2026" or "March 15 2026")
- Vary query strategies — don't repeat the same pattern
- If previous run feedback says certain queries didn't work, avoid similar ones
- Focus on FREE events

Return a JSON object with a "queries" array of strings.
"""


def _format_date_range(weeks_ahead: int) -> str:
    """Format the target date range for the prompt."""
    now = datetime.now()
    end = now + timedelta(weeks=weeks_ahead)
    lines = [f"From {now.strftime('%B %d, %Y')} to {end.strftime('%B %d, %Y')}"]

    # List weekends in the range
    weekends = []
    current = now
    while current <= end:
        if current.weekday() == 5:  # Saturday
            weekends.append(
                f"  - Weekend: {current.strftime('%B %d')}-{(current + timedelta(days=1)).strftime('%d, %Y')}"
            )
        current += timedelta(days=1)

    if weekends:
        lines.append("Key weekends:")
        lines.extend(weekends[:6])  # Cap at 6 weekends

    return "\n".join(lines)


def _format_previous_feedback(last_run: DiscoveryRun | None) -> str:
    """Format previous run results for the prompt."""
    if not last_run:
        return "No previous runs — this is the first discovery for this city."

    parts = [
        f"Last run: {last_run.events_stored} events stored from {last_run.pages_fetched} pages.",
    ]
    if last_run.notes:
        parts.append(f"Feedback: {last_run.notes}")
    if last_run.queries_json:
        try:
            queries = json.loads(last_run.queries_json)
            if queries:
                parts.append("Previous queries used:")
                for q in queries[:10]:
                    if isinstance(q, dict):
                        parts.append(f"  - \"{q.get('query', '')}\" → {q.get('events', 0)} events")
                    else:
                        parts.append(f"  - \"{q}\"")
        except json.JSONDecodeError:
            pass
    return "\n".join(parts)


def generate_queries(
    profile: CityProfile,
    weeks_ahead: int = 2,
    last_run: DiscoveryRun | None = None,
) -> list[str]:
    """Use GPT-4.1-nano to generate search queries informed by city profile."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set, falling back to basic queries")
        return _fallback_queries(profile.city, weeks_ahead)

    try:
        client = OpenAI(api_key=api_key)
        prompt = QUERY_GENERATION_PROMPT.format(
            city=profile.city,
            languages=", ".join(profile.languages) if profile.languages else "English",
            neighborhoods=", ".join(profile.neighborhoods[:10]) if profile.neighborhoods else "N/A",
            venues=", ".join(profile.venues[:10]) if profile.venues else "N/A",
            cultural_patterns=", ".join(profile.cultural_patterns) if profile.cultural_patterns else "N/A",
            event_terms=", ".join(profile.event_terms) if profile.event_terms else "N/A",
            aggregators=", ".join(profile.known_aggregators) if profile.known_aggregators else "N/A",
            seasonal_notes=profile.seasonal_notes or "N/A",
            date_range=_format_date_range(weeks_ahead),
            previous_feedback=_format_previous_feedback(last_run),
        )

        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.5,
            max_tokens=2000,
        )
        content = response.choices[0].message.content
        data = json.loads(content)
        queries = data.get("queries", [])
        if queries:
            logger.info("Generated %d queries for %s", len(queries), profile.city)
            return queries
    except (json.JSONDecodeError, KeyError, IndexError):
        logger.warning("Failed to parse query generation response", exc_info=True)
    except Exception:
        logger.warning("Query generation failed", exc_info=True)

    return _fallback_queries(profile.city, weeks_ahead)


def _fallback_queries(city: str, weeks_ahead: int) -> list[str]:
    """Basic fallback queries when LLM is unavailable."""
    now = datetime.now()
    month = now.strftime("%B %Y")
    return [
        f"free events {city} {month}",
        f"{city} things to do this weekend free",
        f"{city} concerts exhibitions events {month}",
    ]
