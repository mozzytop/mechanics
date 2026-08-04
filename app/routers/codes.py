from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.clients import youtube
from app.config import DEFAULT_LOCATION, missing_keys
from app.repository import list_saved_vehicles, lookup_dtc_code
from app.vehicle_resolve import VehicleResolutionError, resolve_vehicle_from_form, vehicle_spec_str

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/codes", response_class=HTMLResponse)
async def code_lookup_form(request: Request):
    return templates.TemplateResponse(
        "codes.html",
        {
            "request": request,
            "saved_vehicles": list_saved_vehicles(),
            "warnings": missing_keys(),
            "code_info": None,
            "videos": None,
            "resolved_vehicle": None,
            "error": None,
        },
    )


@router.post("/codes", response_class=HTMLResponse)
async def code_lookup_submit(
    request: Request,
    saved_vehicle_id: str = Form(""),
    vin: str = Form(""),
    year: str = Form(""),
    make: str = Form(""),
    model: str = Form(""),
    trim: str = Form(""),
    engine: str = Form(""),
    code: str = Form(...),
):
    error = None
    resolved = None
    code_info = None
    videos = []

    try:
        resolved = await resolve_vehicle_from_form(
            saved_vehicle_id, vin, year, make, model, trim, engine
        )
    except VehicleResolutionError as e:
        error = str(e)

    code_clean = code.strip().upper()

    if not error:
        code_info = lookup_dtc_code(code_clean)
        if not code_info:
            error = f"'{code_clean}' was not found in the local DTC database."

    if resolved and code_info and not error:
        spec = vehicle_spec_str(resolved)
        videos = await youtube.search_repair_videos(spec, code_clean)

    return templates.TemplateResponse(
        "codes.html",
        {
            "request": request,
            "saved_vehicles": list_saved_vehicles(),
            "warnings": missing_keys(),
            "code": code_clean,
            "code_info": code_info,
            "videos": videos,
            "resolved_vehicle": resolved,
            "error": error,
        },
    )
