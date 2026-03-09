import json
import logging
import os

from openai import OpenAI

from src.events.constants import EVENT_CATEGORIES

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Extract free or very low-cost IRL events from the following page text.
Return a JSON object with an "events" array. Each event should have:
- title (str)
- start_time (ISO 8601, Europe/Berlin timezone)
- end_time (ISO 8601, Europe/Berlin timezone)
- location (str, venue name)
- address (str, full address if available)
- description (str, 1-2 sentences)
- is_free (bool, true if genuinely free or very low cost)
- category (str, one of: {categories})

Rules:
- Only include events that are genuinely free or very low cost
- Only include events with concrete dates (not "every Tuesday")
- If no events are found, return {{"events": []}}
- All times must be in Europe/Berlin timezone
""".format(categories=", ".join(EVENT_CATEGORIES))

QUALITY_PROMPT = """Is this a real, specific, interesting event that someone would want to attend?

Event: {title}
Date: {start_time}
Details: {description}

Answer "yes" or "no" only. Filter out:
- Generic listings or directory pages
- Expired or past events
- Paid events disguised as free
- Recurring classes that require registration
"""


def extract_events_from_text(markdown_text: str, source_url: str) -> list[dict]:
    """Use GPT-4.1-nano to extract structured events from page text."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set, skipping extraction")
        return []

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": markdown_text[:8000]},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=2000,
        )
        content = response.choices[0].message.content
        data = json.loads(content)
        events = data.get("events", [])

        # Filter to free events only and add source_url
        result = []
        for event in events:
            if not event.get("is_free", False):
                continue
            if not event.get("title") or not event.get("start_time"):
                continue
            event["source_url"] = source_url
            event["is_paid"] = not event.pop("is_free", True)
            result.append(event)

        return result
    except (json.JSONDecodeError, KeyError, IndexError):
        logger.warning("Failed to parse LLM response for %s", source_url, exc_info=True)
        return []
    except Exception:
        logger.warning("LLM extraction failed for %s", source_url, exc_info=True)
        return []


def assess_event_quality(event: dict) -> bool:
    """Use GPT-4.1-nano to assess if an event is genuinely interesting."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set, skipping quality assessment")
        return False

    try:
        client = OpenAI(api_key=api_key)
        prompt = QUALITY_PROMPT.format(
            title=event.get("title", ""),
            start_time=event.get("start_time", ""),
            description=event.get("description", ""),
        )
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
        )
        answer = response.choices[0].message.content.strip().lower()
        return answer.startswith("yes")
    except Exception:
        logger.warning("Quality assessment failed for event: %s", event.get("title"), exc_info=True)
        return False
