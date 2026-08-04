"""
One-time (or re-runnable) seed script for dtc_codes and
code_to_part_categories.

The app also auto-seeds an empty database on startup (see
app/database.py::init_db), so you normally don't need to run this by hand.
Run it directly when you've hand-edited data/code_to_part_categories.json
and want to pick up the changes without deleting the whole DB file:

    python -m scripts.seed_db
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import _seed_code_to_parts, _seed_dtc_codes, db_session, SCHEMA  # noqa: E402


def main():
    with db_session() as conn:
        conn.executescript(SCHEMA)
        print("Seeding dtc_codes ...")
        _seed_dtc_codes(conn)
        print("Seeding code_to_part_categories ...")
        _seed_code_to_parts(conn)
        dtc_count = conn.execute("SELECT COUNT(*) AS c FROM dtc_codes").fetchone()["c"]
        parts_count = conn.execute(
            "SELECT COUNT(*) AS c FROM code_to_part_categories"
        ).fetchone()["c"]
    print(f"Done. dtc_codes={dtc_count} rows, code_to_part_categories={parts_count} rows.")


if __name__ == "__main__":
    main()
