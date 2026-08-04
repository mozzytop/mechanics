"""Shared logic for turning a submitted form into a resolved vehicle spec.
Used by both the Part Lookup and Code Lookup routers so the "VIN or
Y/M/M/Trim/Engine, or just click a saved vehicle" flow behaves identically
on both pages."""
from typing import Optional

from app.clients import vpic
from app.repository import get_saved_vehicle


class VehicleResolutionError(Exception):
    pass


async def resolve_vehicle_from_form(
    saved_vehicle_id: Optional[str],
    vin: Optional[str],
    year: Optional[str],
    make: Optional[str],
    model: Optional[str],
    trim: Optional[str],
    engine: Optional[str],
) -> dict:
    """Priority: saved vehicle (zero API calls, cached at save time) > VIN >
    manual Y/M/M/Trim/Engine. Raises VehicleResolutionError with a friendly
    message if nothing usable was submitted or vPIC can't confirm it."""
    if saved_vehicle_id:
        saved = get_saved_vehicle(int(saved_vehicle_id))
        if not saved:
            raise VehicleResolutionError("That saved vehicle no longer exists.")
        import json

        return json.loads(saved["resolved_json"])

    if vin and vin.strip():
        try:
            return await vpic.decode_vin(vin.strip())
        except Exception as e:
            raise VehicleResolutionError(f"Could not decode VIN: {e}")

    if year and make and model:
        try:
            return await vpic.decode_ymmte(
                year.strip(), make.strip(), model.strip(), (trim or "").strip(), (engine or "").strip()
            )
        except Exception as e:
            raise VehicleResolutionError(f"Could not verify vehicle: {e}")

    raise VehicleResolutionError(
        "Select a saved vehicle, enter a VIN, or fill in Year/Make/Model."
    )


def vehicle_spec_str(resolved: dict) -> str:
    """Human-readable spec string, e.g. '2015 Honda Civic LX 1.8L', used in
    Gemini prompts, YouTube search queries, and cache keys."""
    parts = [
        str(resolved.get("year", "")),
        resolved.get("make", ""),
        resolved.get("model", ""),
        resolved.get("trim", ""),
        resolved.get("engine", ""),
    ]
    return " ".join(p for p in parts if p).strip()
