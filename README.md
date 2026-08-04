[README.md](https://github.com/user-attachments/files/30721138/README.md)
---
title: Virtual Mechanic
emoji: 🔧
colorFrom: blue
colorTo: gray
sdk: gradio
sdk_version: "6.21.0"
python_version: "3.11"
app_file: app.py
pinned: false
---

# Virtual Mechanic

A personal-use part lookup & OBD-II code lookup tool.

- **Part Lookup** — enter your vehicle + a part name/number, get a comparison
  table of pricing, availability, ratings, and local stores.
- **Code Lookup** — enter your vehicle + an OBD-II code (e.g. `P0420`), get
  the code definition, likely causes, relevant repair videos, and a
  one-click handoff to look up the parts it needs.
- **My Garage** — save your 2-4 regular vehicles so you never re-enter or
  re-decode a VIN twice.

Single-user, local/personal tool. No accounts, no multi-tenant concerns.

## Architecture

Gemini is a **search/compare/formatting layer only** — never a source of
truth for vehicle specs or part fitment. Ground-truth facts come from
deterministic sources first:

```
User input (VIN or Year/Make/Model/Trim/Engine, + part or code)
        │
        ▼
NHTSA vPIC API → resolves exact vehicle spec (cached in SQLite forever)
        │
   ┌────┴─────────────────────────┐
   │ Code Lookup path              │ Part Lookup path
   ▼                                ▼
Local DTC SQLite DB                User-specified part/part number
(code definition, causes,
 linked part categories)
   │                                │
   └──────────────┬─────────────────┘
                   ▼
     Merged structured fact block (vehicle spec + part/code + location)
                   ▼
     Gemini API — grounded search (Google Search + Google Maps)
     Forced JSON output via responseSchema
                   ▼
     Rendered comparison table (price / source / availability /
     rating / distance / link)
```

Gemini never receives anything but already-resolved facts, and is
explicitly instructed not to substitute a different part category and to
exclude any listing it isn't confident matches the exact vehicle.

## Data sources

| Source | Purpose | Auth |
|---|---|---|
| [NHTSA vPIC](https://vpic.nhtsa.dot.gov/api/) | Exact vehicle spec from VIN or Y/M/M | none, free |
| Local SQLite (seeded from [obd-trouble-codes](https://github.com/mytrile/obd-trouble-codes)) | DTC code definitions | none |
| Hand-curated `data/code_to_part_categories.json` | Code → likely causes / part categories | none (maintained by hand — this is where fitment correctness lives) |
| [YouTube Data API v3](https://developers.google.com/youtube/v3) | Repair videos | free API key |
| [Gemini API](https://ai.google.dev/) | Grounded search + structured comparison table | free API key |
| [apiprofile.com AutoPartsAPI](https://apiprofile.com/) (optional) | OE cross-reference lookup | optional key, only if you decide you need it |

### ⚠️ Known upstream data-quality issue in the DTC CSV

The upstream `obd-trouble-codes.csv` (from `github.com/mytrile/obd-trouble-codes`)
has a confirmed row-misalignment bug: starting around `P0409`, a block of
EGR / secondary-air / catalyst / EVAP codes is shifted by one row. For
example, its raw `P0420` row actually contains the description text for
`P0419` — which would mislabel the classic catalytic-converter code as a
Secondary Air Injection relay fault.

To keep the app correct for the codes it's actually built around, all ~113
codes in the hand-curated `data/code_to_part_categories.json` carry a
verified-correct `description` (checked against the SAE J2012 standard
titles) that **overrides** the CSV's description at seed time — this
override re-applies on every app startup, so it self-heals even if you're
upgrading an existing database. The other ~3,000 long-tail codes outside
the curated set still rely on the raw CSV text and may have similar
misalignment in that same P04xx neighborhood — treat those as a starting
point, not gospel, and cross-check anything that looks off. Only the CSV's
`code`/`description` columns are used; the repo's companion `.json` export
of the same data was dropped from this project because it's an unrelated
(and separately malformed) reformatting, not additional data.

## Local setup

```bash
git clone <this repo>
cd virtual-mechanic
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and fill in YOUTUBE_API_KEY, GEMINI_API_KEY, DEFAULT_LOCATION

uvicorn main:app --reload
```

Visit `http://localhost:8000`. The SQLite database and DTC tables are
created and seeded automatically on first startup — no manual migration
step needed. If you later hand-edit `data/code_to_part_categories.json`,
re-apply it with:

```bash
python -m scripts.seed_db
```

### Getting API keys

- **YouTube Data API v3**: [Google Cloud Console](https://console.cloud.google.com/) → enable "YouTube Data API v3" → create an API key. Free tier: 10,000 quota units/day (a search costs 100 units, and results are cached per vehicle+code so repeat lookups are free).
- **Gemini API**: [Google AI Studio](https://aistudio.google.com/apikey) → create a free API key (no credit card required). Uses `gemini-2.5-flash` by default (`GEMINI_MODEL` in `.env`) — this and `gemini-2.5-flash-lite` are the current free-tier Flash models; avoid Pro-tier models, which Google restricted to paid usage in 2026. Model names shift over time, so double check [Google's current free-tier model list](https://ai.google.dev/gemini-api/docs/pricing) if you hit a "model not found" error.
- **AutoPartsAPI (optional)**: [apiprofile.com](https://apiprofile.com/) → 100 free requests/month. Only add this if NHTSA + Gemini's grounded search aren't giving you good OE cross-reference numbers for your specific vehicle — test their playground with your actual vehicle first.

⚠️ Never commit `.env` or paste API keys into chat/screenshots. If a key is
ever exposed that way, regenerate it immediately in the provider's
dashboard before using it again.

## Deploying to Hugging Face Spaces

This repo is ready to deploy as-is, using the **Gradio SDK** (not Docker —
Docker Spaces now require a verified payment method on file, even though
CPU-basic usage is free; the Gradio SDK is a plain Python environment that
runs our FastAPI app just fine without that requirement). A `Dockerfile` is
also included in this repo if you ever do want to deploy with Docker
instead (e.g. on your own server, or once you've verified payment on HF).

1. Create a new Space, choosing **Gradio** as the SDK (the `sdk: gradio` /
   `app_file: app.py` lines in this README's frontmatter do this
   automatically if you push straight to a Space repo).
2. Push this repo's contents to the Space (`app.py` at the repo root is
   the entrypoint Spaces will run — it just boots the real app from
   `main.py` with uvicorn on port 7860, no Gradio UI involved).
3. In the Space's **Settings → Variables and secrets**, add
   `YOUTUBE_API_KEY`, `GEMINI_API_KEY`, `DEFAULT_LOCATION`, and (optionally)
   `AUTOPARTS_API_KEY` — do **not** put real keys in `.env` inside the repo.
4. The Space installs `requirements.txt` automatically and runs
   `python app.py`, which listens on port `7860` (HF's expected port).

Note: Spaces storage is ephemeral by default — your `saved_vehicles`,
`vehicle_cache`, `youtube_cache`, and `part_search_cache` tables will reset
on a rebuild/restart unless you attach a [persistent storage
volume](https://huggingface.co/docs/hub/spaces-storage) in the Space
settings. For truly personal use, running it locally keeps your garage and
caches permanent for free.

## Project layout

```
main.py                          FastAPI app entrypoint
app/
  config.py                      Loads .env, exposes settings
  database.py                    SQLite schema, connection, auto-seed
  repository.py                  Saved-vehicle & DTC-code data access
  vehicle_resolve.py             Shared "which vehicle did they mean" logic
  clients/
    vpic.py                      NHTSA vPIC client + cache
    youtube.py                   YouTube Data API client + cache
    gemini.py                    Gemini grounded search + JSON schema client
    autoparts.py                 Optional apiprofile.com client (unused by default)
  routers/
    lookup.py                    GET/POST /        (Part Lookup Tool)
    codes.py                     GET/POST /codes    (Code Lookup Tool)
    garage.py                    GET /garage, saved-vehicle CRUD
  templates/                     Jinja2 templates
  static/style.css               Styling
data/
  obd-trouble-codes.csv          Static DTC reference data (seeded at startup)
  code_to_part_categories.json   Hand-curated code → causes/parts mapping
scripts/seed_db.py                Standalone re-seed script
```

## Non-goals

No user accounts, no multi-user support, no production hardening (rate
limiting, WAF, etc.), no live inventory guarantees — every price/stock
figure is a search-time snapshot, not a live feed.
