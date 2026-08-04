"""
NHTSA vPIC client. No API key required. Ground truth for exact vehicle
spec (make/model/year/engine/trim). Results are cached forever in SQLite
since a VIN's decoded spec never changes.
"""
import json
from typing import Optional

import httpx

from app.database import db_session

BASE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles"


def _cache_key_for_vin(vin: str) -> str:
    return f"vin:{vin.upper().strip()}"


def _cache_key_for_ymm(year: str, make: str, model: str, trim: str, engine: str) -> str:
    return f"ymm:{year}|{make}|{model}|{trim}|{engine}".lower()


def _get_cached(cache_key: str) -> Optional[dict]:
    with db_session() as conn:
        row = conn.execute(
            "SELECT resolved_json FROM vehicle_cache WHERE cache_key = ?", (cache_key,)
        ).fetchone()
    return json.loads(row["resolved_json"]) if row else None


def _set_cached(cache_key: str, resolved: dict) -> None:
    with db_session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO vehicle_cache (cache_key, resolved_json) VALUES (?, ?)",
            (cache_key, json.dumps(resolved)),
        )


async def decode_vin(vin: str) -> dict:
    """Resolve a VIN to a clean vehicle spec dict. Cached by VIN — a VIN we've
    already resolved is never re-sent to vPIC."""
    cache_key = _cache_key_for_vin(vin)
    cached = _get_cached(cache_key)
    if cached:
        return cached

    url = f"{BASE_URL}/DecodeVinValues/{vin}?format=json"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    raw = data.get("Results", [{}])[0]
    resolved = _clean_vpic_result(raw, vin=vin)
    _set_cached(cache_key, resolved)
    return resolved


async def decode_ymmte(year: str, make: str, model: str, trim: str = "", engine: str = "") -> dict:
    """Resolve a manual Year/Make/Model/Trim/Engine entry. Cached by the
    combo so repeat manual entries never re-hit vPIC either."""
    cache_key = _cache_key_for_ymm(year, make, model, trim, engine)
    cached = _get_cached(cache_key)
    if cached:
        return cached

    # vPIC doesn't have a single "decode YMM to full spec" endpoint the way
    # VIN decode does, but GetModelsForMakeYear confirms the make/model/year
    # combination is real (ground truth), which is what we actually need —
    # trim/engine are free-text refinements the user already knows.
    url = (
        f"{BASE_URL}/GetModelsForMakeYear/make/{make}/modelyear/{year}?format=json"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("Results", [])
    matched = next(
        (r for r in results if r.get("Model_Name", "").strip().lower() == model.strip().lower()),
        None,
    )

    resolved = {
        "vin": None,
        "year": year,
        "make": make,
        "model": matched["Model_Name"] if matched else model,
        "trim": trim,
        "engine": engine,
        "verified_by_nhtsa": matched is not None,
        "raw": matched or {},
    }
    _set_cached(cache_key, resolved)
    return resolved


def _clean_vpic_result(raw: dict, vin: str) -> dict:
    return {
        "vin": vin.upper().strip(),
        "year": raw.get("ModelYear") or "",
        "make": raw.get("Make") or "",
        "model": raw.get("Model") or "",
        "trim": raw.get("Trim") or raw.get("Series") or "",
        "engine": _engine_summary(raw),
        "verified_by_nhtsa": True,
        "raw": raw,
    }


def _engine_summary(raw: dict) -> str:
    parts = []
    if raw.get("DisplacementL"):
        parts.append(f"{raw['DisplacementL']}L")
    if raw.get("EngineCylinders"):
        parts.append(f"{raw['EngineCylinders']}-cyl")
    if raw.get("EngineModel"):
        parts.append(raw["EngineModel"])
    if raw.get("FuelTypePrimary"):
        parts.append(raw["FuelTypePrimary"])
    return " ".join(parts).strip()


async def get_makes() -> list[str]:
    url = f"{BASE_URL}/GetAllMakes?format=json"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    return sorted({r["Make_Name"] for r in data.get("Results", []) if r.get("Make_Name")})


async def get_models_for_make_year(make: str, year: str) -> list[str]:
    url = f"{BASE_URL}/GetModelsForMakeYear/make/{make}/modelyear/{year}?format=json"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    return sorted({r["Model_Name"] for r in data.get("Results", []) if r.get("Model_Name")})
