"""
Virtual Mechanic — personal-use part lookup & OBD-II code lookup tool.

Run locally:
    pip install -r requirements.txt
    cp .env.example .env   # then fill in your API keys
    uvicorn main:app --reload

Run on Hugging Face Spaces: see README.md (Docker SDK, port 7860).
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routers import codes, garage, lookup

app = FastAPI(title="Virtual Mechanic", description="Personal part & OBD-II code lookup tool")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(lookup.router)
app.include_router(codes.router)
app.include_router(garage.router)


@app.on_event("startup")
async def on_startup():
    init_db()
