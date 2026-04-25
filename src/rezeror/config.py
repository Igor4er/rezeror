from __future__ import annotations

import os
from pathlib import Path


MIN_SESSION_SECRET_LENGTH = 32


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    if not raw:
        return default

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate
    return (PROJECT_ROOT / candidate).resolve()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = _env_path("REZEROR_DATA_DIR", PROJECT_ROOT / "data")
CHAPTERS_DIR = DATA_DIR / "chapters"
STATE_DIR = DATA_DIR / "state"
MANIFEST_PATH = STATE_DIR / "manifest.json"
SYNC_STATE_PATH = STATE_DIR / "sync_state.json"
PROGRESS_DB_PATH = _env_path("REZEROR_DB_PATH", DATA_DIR / "progress.sqlite3")
TOC_URL = "https://witchculttranslation.com/table-of-content/"
USER_AGENT = "rezeror-bot/0.1 (+https://github.com/Igor4er/rezeror)"


def owner_auth_enabled() -> bool:
    return bool(os.getenv("REZEROR_OWNER_PASSWORD") or os.getenv("REZEROR_OWNER_PASSWORD_HASH"))


def owner_credentials() -> tuple[str, str]:
    username = os.getenv("REZEROR_OWNER_USERNAME", "owner")
    password = os.getenv("REZEROR_OWNER_PASSWORD", "")
    return username, password


def owner_password_hash() -> str:
    return os.getenv("REZEROR_OWNER_PASSWORD_HASH", "")


def session_secret() -> str:
    secret = os.getenv("REZEROR_SESSION_SECRET", "")
    if not secret:
        raise ValueError("REZEROR_SESSION_SECRET must be configured")
    if len(secret) < MIN_SESSION_SECRET_LENGTH:
        raise ValueError(f"REZEROR_SESSION_SECRET must be at least {MIN_SESSION_SECRET_LENGTH} characters")
    return secret


def owner_session_days() -> int:
    raw = os.getenv("REZEROR_OWNER_SESSION_DAYS", "30")
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return 30
    return max(1, min(days, 30))


def ensure_data_dirs() -> None:
    CHAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
