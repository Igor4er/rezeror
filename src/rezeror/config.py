from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CHAPTERS_DIR = DATA_DIR / "chapters"
STATE_DIR = DATA_DIR / "state"
MANIFEST_PATH = STATE_DIR / "manifest.json"
SYNC_STATE_PATH = STATE_DIR / "sync_state.json"
PROGRESS_DB_PATH = DATA_DIR / "progress.sqlite3"
TOC_URL = "https://witchculttranslation.com/table-of-content/"
USER_AGENT = "rezeror-bot/0.1 (+https://github.com/example/rezeror)"


def ensure_data_dirs() -> None:
    CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
