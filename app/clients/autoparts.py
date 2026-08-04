"""
Optional supplemental fitment/cross-reference client for apiprofile.com's
AutoPartsAPI (free tier: 100 req/month, 1 req/sec).

Not wired into either page by default — the build prompt is explicit that
this is a fallback for when NHTSA + Gemini's grounded search aren't enough
for OE cross-reference numbers, and that you should test the playground
with your actual vehicle before building around it. Kept here so it's a
one-line addition to routers/lookup.py if/when you decide you need it.

SECURITY NOTE: if you ever had an AUTOPARTS_API_KEY that was shared in a
screenshot or any other non-.env channel, treat it as compromised and
regenerate it in the apiprofile.com dashboard before putting a new value
in your .env file. Never commit the key or log it.
"""
from typing import Optional

import httpx

from app.config import AUTOPARTS_API_KEY

BASE_URL = "https://auto-parts-catalog.apiprofile.com/api"


async def cross_reference_lookup(part_number: str) -> Optional[dict]:
    """Look up OE cross-reference numbers for a part number. Returns None
    if no key is configured or the call fails."""
    if not AUTOPARTS_API_KEY:
        return None
    headers = {"x-apiprofile-key": AUTOPARTS_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{BASE_URL}/parts/{part_number}/cross-reference", headers=headers
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError:
        return None
