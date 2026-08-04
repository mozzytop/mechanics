"""
YouTube Data API v3 client. search.list costs 100 quota units/call against a
10,000/day budget, so results are cached per (vehicle spec + code) combo in
SQLite — a repeat lookup for the same vehicle+code never re-spends quota.
"""
import json
from typing import Optional

import httpx

from app.config import YOUTUBE_API_KEY
from app.database import db_session

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def _cache_key(vehicle_spec: str, code: str) -> str:
    return f"{vehicle_spec}|{code}".lower().strip()


def _get_cached(cache_key: str) -> Optional[list]:
    with db_session() as conn:
        row = conn.execute(
            "SELECT results_json FROM youtube_cache WHERE cache_key = ?", (cache_key,)
        ).fetchone()
    return json.loads(row["results_json"]) if row else None


def _set_cached(cache_key: str, results: list) -> None:
    with db_session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO youtube_cache (cache_key, results_json) VALUES (?, ?)",
            (cache_key, json.dumps(results)),
        )


async def search_repair_videos(vehicle_spec: str, code: str, max_results: int = 6) -> list[dict]:
    """vehicle_spec should already be a clean human string, e.g.
    '2015 Honda Civic 1.8L'. Returns [] gracefully if no API key is set or
    the request fails, rather than breaking the whole page."""
    if not YOUTUBE_API_KEY:
        return []

    cache_key = _cache_key(vehicle_spec, code)
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    query = f"{vehicle_spec} {code} fix repair"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "key": YOUTUBE_API_KEY,
        "relevanceLanguage": "en",
        "safeSearch": "moderate",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        return []

    results = []
    for item in data.get("items", []):
        vid = item.get("id", {}).get("videoId")
        snippet = item.get("snippet", {})
        if not vid:
            continue
        results.append(
            {
                "video_id": vid,
                "title": snippet.get("title", ""),
                "channel_title": snippet.get("channelTitle", ""),
                "thumbnail": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
                "url": f"https://youtube.com/watch?v={vid}",
            }
        )

    _set_cached(cache_key, results)
    return results
