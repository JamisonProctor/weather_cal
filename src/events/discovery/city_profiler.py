"""LLM-generated city profiles for informed event discovery."""

import json
import logging
import os
import uuid
from datetime import datetime

from openai import OpenAI

from src.events.sources import CityProfile, get_city_profile, save_city_profile

logger = logging.getLogger(__name__)

CITY_PROFILE_PROMPT = """You are an expert on city culture and local events. Generate a detailed profile of {city} that will help discover free local events.

Return a JSON object with these fields:
- "languages": array of languages used locally (most common first), e.g. ["German", "English"]
- "neighborhoods": array of 8-15 neighborhoods/districts known for cultural activity
- "venues": array of 10-20 parks, cultural centers, markets, galleries, plazas, and community spaces that host free events
- "cultural_patterns": array of 5-10 types of free events typical for this city (e.g. "Biergarten live music", "outdoor cinema", "flea markets")
- "event_terms": array of 10-15 local-language terms for events and free admission (e.g. "Veranstaltung", "Eintritt frei", "Flohmarkt")
- "known_aggregators": array of 3-8 local websites/URLs that aggregate event listings for this city
- "seasonal_notes": string describing what kinds of events happen in the current season ({month} {year})

Focus on FREE events and cultural happenings. Be specific to {city} — not generic.
Return ONLY the JSON object, no other text.
"""


def generate_city_profile(city: str, month: str = "", year: str = "") -> dict:
    """Call GPT-4.1-nano to generate a city profile. Returns parsed dict."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set, cannot generate city profile")
        return {}

    if not month:
        now = datetime.now()
        month = now.strftime("%B")
        year = str(now.year)

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {
                    "role": "user",
                    "content": CITY_PROFILE_PROMPT.format(
                        city=city, month=month, year=year
                    ),
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=2000,
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except (json.JSONDecodeError, KeyError, IndexError):
        logger.warning("Failed to parse city profile response", exc_info=True)
        return {}
    except Exception:
        logger.warning("City profile generation failed for %s", city, exc_info=True)
        return {}


def get_or_create_profile(db_path: str, city: str) -> CityProfile | None:
    """Load existing city profile or generate and save a new one."""
    profile = get_city_profile(db_path, city)
    if profile:
        logger.info("Loaded existing profile for %s", city)
        return profile

    logger.info("Generating new city profile for %s", city)
    data = generate_city_profile(city)
    if not data:
        return None

    profile = CityProfile(
        id=str(uuid.uuid4()),
        city=city,
        languages=data.get("languages", []),
        neighborhoods=data.get("neighborhoods", []),
        venues=data.get("venues", []),
        cultural_patterns=data.get("cultural_patterns", []),
        event_terms=data.get("event_terms", []),
        known_aggregators=data.get("known_aggregators", []),
        seasonal_notes=data.get("seasonal_notes", ""),
    )
    save_city_profile(db_path, profile)
    logger.info("Saved new city profile for %s", city)
    return profile
