from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.clients import gemini
from app.config import DEFAULT_LOCATION, missing_keys
from app.repository import list_saved_vehicles
from app.vehicle_resolve import VehicleResolutionError, resolve_vehicle_from_form, vehicle_spec_str

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def part_lookup_form(
    request: Request,
    # Optional pre-fill params, used by the "Find these parts" handoff from /codes
    part: str = "",
    year: str = "",
    make: str = "",
    model: str = "",
    trim: str = "",
    engine: str = "",
):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "saved_vehicles": list_saved_vehicles(),
            "default_location": DEFAULT_LOCATION,
            "warnings": missing_keys(),
            "prefill": {
                "part": part,
                "year": year,
                "make": make,
                "model": model,
                "trim": trim,
                "engine": engine,
            },
            "results": None,
            "error": None,
        },
    )


@router.post("/", response_class=HTMLResponse)
async def part_lookup_submit(
    request: Request,
    saved_vehicle_id: str = Form(""),
    vin: str = Form(""),
    year: str = Form(""),
    make: str = Form(""),
    model: str = Form(""),
    trim: str = Form(""),
    engine: str = Form(""),
    part: str = Form(...),
    location: str = Form(""),
):
    error = None
    results = None
    resolved = None
    location = location.strip() or DEFAULT_LOCATION

    try:
        resolved = await resolve_vehicle_from_form(
            saved_vehicle_id, vin, year, make, model, trim, engine
        )
    except VehicleResolutionError as e:
        error = str(e)

    if resolved and not error:
        spec = vehicle_spec_str(resolved)
        results = await gemini.compare_part_sources(
            year=str(resolved.get("year", "")),
            make=resolved.get("make", ""),
            model=resolved.get("model", ""),
            trim=resolved.get("trim", ""),
            engine=resolved.get("engine", ""),
            part=part.strip(),
            location=location,
        )
        if not results:
            error = (
                "No confident matches found (or GEMINI_API_KEY is not configured). "
                "Try a more specific part name or number."
            )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "saved_vehicles": list_saved_vehicles(),
            "default_location": DEFAULT_LOCATION,
            "warnings": missing_keys(),
            "prefill": {
                "part": part,
                "year": year,
                "make": make,
                "model": model,
                "trim": trim,
                "engine": engine,
            },
            "resolved_vehicle": resolved,
            "location": location,
            "part": part,
            "results": results,
            "error": error,
        },
    )
