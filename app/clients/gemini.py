"""
Gemini client. Gemini is used ONLY as a search/compare/formatting layer —
it never receives anything but already-resolved ground-truth facts (exact
vehicle spec from vPIC, exact part name/number the user typed, and the
user's location), and it must return structured JSON matching a fixed
schema. It is not allowed to invent or "correct" the vehicle spec or part
category.

Implementation note: the Gemini API does not currently allow combining
built-in grounding tools (google_search / google_maps) with a forced
`responseSchema` in the *same* call — grounding tool calls require free-form
text output. So this client does it in two steps:

  1. A grounded call (google_search + google_maps tools enabled) that asks
     the model, in a plain-text prompt, to research pricing/availability and
     report its findings.
  2. A second, tool-free structuring call that takes the grounded text from
     step 1 and forces it into `responseSchema` JSON. This call is NOT
     allowed to add any new facts — only to reformat what step 1 found.

Results are cached in SQLite per (vehicle spec + part + location) so a
repeat lookup costs zero API calls.
"""
import json
import logging
from typing import Optional

import httpx

from app.config import GEMINI_MODEL
from app.database import db_session

logger = logging.getLogger(__name__)

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_name": {"type": "string"},
                    "source_type": {"type": "string", "enum": ["online", "local"]},
                    "part_description": {"type": "string"},
                    "price": {"type": "string"},
                    "in_stock": {"type": "string"},
                    "rating": {"type": ["number", "null"]},
                    "distance_miles": {"type": ["number", "null"]},
                    "url": {"type": "string"},
                },
                "required": [
                    "source_name",
                    "source_type",
                    "part_description",
                    "price",
                    "in_stock",
                    "url",
                ],
            },
        }
    },
    "required": ["results"],
}


def _cache_key(vehicle_spec: str, part: str, location: str) -> str:
    return f"{vehicle_spec}|{part}|{location}".lower().strip()


def _get_cached(cache_key: str) -> Optional[list]:
    with db_session() as conn:
        row = conn.execute(
            "SELECT results_json FROM part_search_cache WHERE cache_key = ?", (cache_key,)
        ).fetchone()
    return json.loads(row["results_json"]) if row else None


def _set_cached(cache_key: str, results: list) -> None:
    with db_session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO part_search_cache (cache_key, results_json) VALUES (?, ?)",
            (cache_key, json.dumps(results)),
        )


def _build_search_prompt(year, make, model, trim, engine, part, location) -> str:
    return f"""Vehicle: {year} {make} {model} {trim}, engine {engine}
Part needed: {part}
User location: {location}

Search for this exact part for this exact vehicle. Compare online retailers
and local auto parts stores near the user's location. For each result note:
the source/store name, whether it's an online retailer or a local store,
the specific part description found, price, stock status, rating if shown,
approximate distance in miles if it's a local store, and the direct URL.

Do not substitute a different part category than the one specified. If you
are not confident a listing matches this exact vehicle's fitment, exclude
it rather than guess. Report only what you actually find via search."""


def _build_structuring_prompt(grounded_text: str) -> str:
    return f"""Convert the following research notes into the required JSON
structure. Do not add, invent, or infer any facts that are not already
present in the notes below — only reformat them. If a field wasn't
mentioned (e.g. no rating given), use null.

RESEARCH NOTES:
{grounded_text}"""


async def _call_gemini(payload: dict, api_key: str) -> dict:
    url = f"{API_BASE}/{GEMINI_MODEL}:generateContent?key={api_key}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


def _extract_text(response: dict) -> str:
    try:
        parts = response["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError):
        return ""


async def compare_part_sources(
    year: str, make: str, model: str, trim: str, engine: str, part: str, location: str
) -> list[dict]:
    """Returns a list of structured result rows matching RESULT_SCHEMA's
    'results' array. Returns [] if GEMINI_API_KEY is unset or a call fails,
    so the page can render a friendly empty state instead of crashing."""
    # Read the key at call time (not import time) so HF Spaces secrets
    # that are injected after module import are picked up.
    import os
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        logger.warning("GEMINI_API_KEY is not set — skipping part search.")
        return []

    vehicle_spec = f"{year} {make} {model} {trim}".strip()
    cache_key = _cache_key(vehicle_spec, part, location)
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    search_prompt = _build_search_prompt(year, make, model, trim, engine, part, location)

    try:
        # Step 1: grounded search (free-text output).
        grounded_payload = {
            "contents": [{"role": "user", "parts": [{"text": search_prompt}]}],
            "tools": [{"google_search": {}}, {"google_maps": {}}],
        }
        grounded_response = await _call_gemini(grounded_payload, api_key)
        grounded_text = _extract_text(grounded_response)
        if not grounded_text.strip():
            logger.warning("Gemini grounded search returned empty text.")
            return []

        # Step 2: structure the grounded findings into forced JSON.
        structuring_payload = {
            "contents": [
                {"role": "user", "parts": [{"text": _build_structuring_prompt(grounded_text)}]}
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": RESULT_SCHEMA,
            },
        }
        structured_response = await _call_gemini(structuring_payload, api_key)
        structured_text = _extract_text(structured_response)
        parsed = json.loads(structured_text) if structured_text else {"results": []}
        results = parsed.get("results", [])
    except httpx.HTTPStatusError as e:
        logger.error("Gemini API HTTP error %s: %s", e.response.status_code, e.response.text[:500])
        return []
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
        logger.error("Gemini API call failed: %s", e)
        return []

    _set_cached(cache_key, results)
    return results
