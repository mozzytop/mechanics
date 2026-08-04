"""
SQLite layer. One file, a handful of tables:

  dtc_codes              - static reference data seeded from the GitHub CSV
  code_to_part_categories- hand-curated code -> likely_causes/part_categories
  vehicle_cache           - vPIC results cached by VIN or Y/M/M/Trim/Engine key
  saved_vehicles          - "My Garage" quick-select vehicles
  youtube_cache           - cached YouTube search results per (vehicle+code)
  part_search_cache       - cached Gemini comparison results per (vehicle+part+location)

Everything is deterministic ground truth except the two *_cache tables for
external APIs, which exist purely to avoid re-spending quota/cost on repeat
lookups (never re-call vPIC/YouTube/Gemini for a query already answered).
"""
import csv
import json
import sqlite3
from contextlib import contextmanager

from app.config import DATABASE_PATH, DTC_CSV_PATH, CODE_TO_PARTS_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS dtc_codes (
    code TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS code_to_part_categories (
    code TEXT PRIMARY KEY,
    likely_causes TEXT NOT NULL,      -- JSON array
    part_categories TEXT NOT NULL     -- JSON array
    -- Intentionally no FK to dtc_codes: the upstream CSV (from
    -- github.com/mytrile/obd-trouble-codes) is missing some codes we still
    -- want to hand-curate (e.g. several C0/U0/B0 codes), so dtc_codes gets
    -- backfilled with a minimal row for any curated-only code at seed time.
);

CREATE TABLE IF NOT EXISTS vehicle_cache (
    cache_key TEXT PRIMARY KEY,       -- VIN, or "year|make|model|trim|engine"
    resolved_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS saved_vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname TEXT NOT NULL,
    vin TEXT,
    year TEXT,
    make TEXT,
    model TEXT,
    trim TEXT,
    engine TEXT,
    resolved_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS youtube_cache (
    cache_key TEXT PRIMARY KEY,       -- "vehicle_spec|code"
    results_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS part_search_cache (
    cache_key TEXT PRIMARY KEY,       -- "vehicle_spec|part|location"
    results_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_db() -> None:
    """Create tables if needed, then seed dtc_codes / code_to_part_categories
    if they're empty. Safe to call on every app startup. The curated
    description-override step always re-runs (cheap, idempotent) so an
    existing database self-heals if it was seeded before a curated
    description was corrected."""
    with db_session() as conn:
        conn.executescript(SCHEMA)
        count = conn.execute("SELECT COUNT(*) AS c FROM dtc_codes").fetchone()["c"]
        if count == 0:
            _seed_dtc_codes(conn)
        count2 = conn.execute("SELECT COUNT(*) AS c FROM code_to_part_categories").fetchone()["c"]
        if count2 == 0:
            _seed_code_to_parts(conn)
        else:
            _apply_description_overrides(conn)


def _classify(code: str) -> str:
    """Generic (SAE-defined) codes have a 0 as the 2nd digit; manufacturer
    specific codes have a 1, 2, or 3. Simple, deterministic, no LLM needed."""
    if len(code) >= 2 and code[1] in "0":
        return "generic"
    return "manufacturer-specific"


def _seed_dtc_codes(conn: sqlite3.Connection) -> None:
    if not DTC_CSV_PATH.exists():
        return
    rows = []
    with open(DTC_CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue
            code, description = row[0].strip(), row[1].strip()
            if not code:
                continue
            rows.append((code, description, _classify(code)))
    conn.executemany(
        "INSERT OR IGNORE INTO dtc_codes (code, description, category) VALUES (?, ?, ?)",
        rows,
    )


def _seed_code_to_parts(conn: sqlite3.Connection) -> None:
    if not CODE_TO_PARTS_PATH.exists():
        return
    with open(CODE_TO_PARTS_PATH, encoding="utf-8") as f:
        mapping = json.load(f)

    # The upstream CSV (github.com/mytrile/obd-trouble-codes) doesn't cover
    # every code we've hand-curated (mostly newer P0-extension, C0/U0/B0
    # codes). Backfill dtc_codes with a minimal row for any curated code
    # that isn't already present, using the description we curated for it,
    # so lookups for those codes still resolve instead of 404ing.
    existing = {r["code"] for r in conn.execute("SELECT code FROM dtc_codes").fetchall()}
    backfill_rows = []
    for code, v in mapping.items():
        if code not in existing and v.get("description"):
            backfill_rows.append((code, v["description"], _classify(code)))
    if backfill_rows:
        conn.executemany(
            "INSERT OR IGNORE INTO dtc_codes (code, description, category) VALUES (?, ?, ?)",
            backfill_rows,
        )

    rows = [
        (code, json.dumps(v.get("likely_causes", [])), json.dumps(v.get("part_categories", [])))
        for code, v in mapping.items()
    ]
    conn.executemany(
        """INSERT OR REPLACE INTO code_to_part_categories (code, likely_causes, part_categories)
           VALUES (?, ?, ?)""",
        rows,
    )

    _apply_description_overrides(conn, mapping=mapping)


def _apply_description_overrides(conn: sqlite3.Connection, mapping: dict | None = None) -> None:
    """Prefer our verified-correct curated description over the CSV's for
    every code we hand-maintain. The upstream CSV
    (github.com/mytrile/obd-trouble-codes) has a confirmed row-misalignment
    bug affecting a block of P04xx codes (EGR/secondary air/catalyst/EVAP) —
    e.g. its 'P0420' row actually contains the text for P0419. See
    data/code_to_part_categories.json and the README for details. This is
    idempotent and cheap, so it's safe to call on every startup."""
    if mapping is None:
        if not CODE_TO_PARTS_PATH.exists():
            return
        with open(CODE_TO_PARTS_PATH, encoding="utf-8") as f:
            mapping = json.load(f)
    override_rows = [(v["description"], code) for code, v in mapping.items() if v.get("description")]
    if override_rows:
        conn.executemany("UPDATE dtc_codes SET description = ? WHERE code = ?", override_rows)
