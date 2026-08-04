"""
Central configuration. All secrets are loaded from environment variables
(via a local .env file) and are never hardcoded or logged.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
AUTOPARTS_API_KEY = os.getenv("AUTOPARTS_API_KEY", "")
DEFAULT_LOCATION = os.getenv("DEFAULT_LOCATION", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

_db_path = os.getenv("DATABASE_PATH", "data/virtual_mechanic.db")
DATABASE_PATH = str((BASE_DIR / _db_path).resolve()) if not os.path.isabs(_db_path) else _db_path

DTC_CSV_PATH = BASE_DIR / "data" / "obd-trouble-codes.csv"
CODE_TO_PARTS_PATH = BASE_DIR / "data" / "code_to_part_categories.json"


def missing_keys() -> list[str]:
    """Return a list of human-readable warnings for unset keys, used to
    surface friendly banners in the UI instead of failing silently."""
    warnings = []
    if not YOUTUBE_API_KEY:
        warnings.append("YOUTUBE_API_KEY is not set — video results will be skipped.")
    if not GEMINI_API_KEY:
        warnings.append("GEMINI_API_KEY is not set — part lookup/comparison will not work.")
    return warnings
