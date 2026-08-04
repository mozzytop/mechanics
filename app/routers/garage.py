import json

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.clients import vpic
from app.repository import delete_saved_vehicle, list_saved_vehicles, save_vehicle

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/garage", response_class=HTMLResponse)
async def garage_list(request: Request):
    return templates.TemplateResponse(
        "garage.html",
        {
            "request": request,
            "saved_vehicles": list_saved_vehicles(),
            "resolved": None,
            "error": None,
        },
    )


@router.post("/garage/resolve", response_class=HTMLResponse)
async def garage_resolve(
    request: Request,
    vin: str = Form(""),
    year: str = Form(""),
    make: str = Form(""),
    model: str = Form(""),
    trim: str = Form(""),
    engine: str = Form(""),
):
    """Step 1 of 'Add new vehicle': resolve via vPIC and show a confirm
    screen before saving, per the build spec."""
    error = None
    resolved = None
    try:
        if vin.strip():
            resolved = await vpic.decode_vin(vin.strip())
        elif year and make and model:
            resolved = await vpic.decode_ymmte(
                year.strip(), make.strip(), model.strip(), trim.strip(), engine.strip()
            )
        else:
            error = "Enter a VIN or Year/Make/Model."
    except Exception as e:
        error = f"Could not resolve vehicle: {e}"

    return templates.TemplateResponse(
        "garage.html",
        {
            "request": request,
            "saved_vehicles": list_saved_vehicles(),
            "resolved": resolved,
            "error": error,
        },
    )


@router.post("/garage/save")
async def garage_save(
    nickname: str = Form(...),
    resolved_json: str = Form(...),
    vin: str = Form(""),
):
    """Step 2 of 'Add new vehicle': persist the already-resolved spec (no
    second vPIC call — the confirm screen posts back the full resolved JSON
    from step 1 via a hidden field)."""
    resolved = json.loads(resolved_json)
    save_vehicle(nickname=nickname.strip(), resolved=resolved, vin=vin or resolved.get("vin"))
    return RedirectResponse(url="/garage", status_code=303)


@router.post("/garage/delete/{vehicle_id}")
async def garage_delete(vehicle_id: int):
    delete_saved_vehicle(vehicle_id)
    return RedirectResponse(url="/garage", status_code=303)
