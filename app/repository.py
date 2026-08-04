"""Data access helpers for saved_vehicles and the local dtc_codes /
code_to_part_categories tables. Kept separate from database.py (schema/
connection plumbing) to keep each file focused."""
import json
from typing import Optional

from app.database import db_session


# ---------------------------------------------------------------------------
# Saved vehicles ("My Garage")
# ---------------------------------------------------------------------------

def list_saved_vehicles() -> list[dict]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM saved_vehicles ORDER BY created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_saved_vehicle(vehicle_id: int) -> Optional[dict]:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM saved_vehicles WHERE id = ?", (vehicle_id,)
        ).fetchone()
    return dict(row) if row else None


def save_vehicle(
    nickname: str,
    resolved: dict,
    vin: Optional[str] = None,
) -> int:
    with db_session() as conn:
        cur = conn.execute(
            """INSERT INTO saved_vehicles
               (nickname, vin, year, make, model, trim, engine, resolved_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                nickname,
                vin,
                str(resolved.get("year", "")),
                resolved.get("make", ""),
                resolved.get("model", ""),
                resolved.get("trim", ""),
                resolved.get("engine", ""),
                json.dumps(resolved),
            ),
        )
        return cur.lastrowid


def delete_saved_vehicle(vehicle_id: int) -> None:
    with db_session() as conn:
        conn.execute("DELETE FROM saved_vehicles WHERE id = ?", (vehicle_id,))


# ---------------------------------------------------------------------------
# DTC codes (local, deterministic — never re-sourced from an external API)
# ---------------------------------------------------------------------------

def lookup_dtc_code(code: str) -> Optional[dict]:
    code = code.strip().upper()
    with db_session() as conn:
        dtc_row = conn.execute(
            "SELECT * FROM dtc_codes WHERE code = ?", (code,)
        ).fetchone()
        parts_row = conn.execute(
            "SELECT * FROM code_to_part_categories WHERE code = ?", (code,)
        ).fetchone()

    if not dtc_row:
        return None

    result = dict(dtc_row)
    if parts_row:
        result["likely_causes"] = json.loads(parts_row["likely_causes"])
        result["part_categories"] = json.loads(parts_row["part_categories"])
    else:
        result["likely_causes"] = []
        result["part_categories"] = []
    return result
