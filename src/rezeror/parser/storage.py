from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from rezeror.config import CHAPTERS_DIR, MANIFEST_PATH, SYNC_STATE_PATH, ensure_data_dirs
from rezeror.parser.models import TocEntry

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    lowered = value.lower().strip()
    normalized = _SLUG_RE.sub("-", lowered).strip("-")
    return normalized or "item"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def load_state() -> dict[str, Any]:
    ensure_data_dirs()
    return load_json(
        SYNC_STATE_PATH,
        {
            "entries": {},
            "last_toc_hash": "",
            "last_sync_at": None,
        },
    )


def save_state(state: dict[str, Any]) -> None:
    save_json(SYNC_STATE_PATH, state)


def chapter_file_path(entry: TocEntry) -> Path:
    key_hash = sha256(entry.identity_key.encode("utf-8")).hexdigest()[:10]
    arc_folder = slugify(entry.arc)
    chapter_slug = slugify(entry.chapter)
    filename = f"{chapter_slug}-{key_hash}.md"
    return Path(arc_folder) / filename


def write_markdown_chapter(
    entry: TocEntry,
    markdown_text: str,
    markdown_hash: str,
    fetched_at: str,
) -> str:
    ensure_data_dirs()
    rel_path = chapter_file_path(entry)
    abs_path = CHAPTERS_DIR / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)

    metadata = {
        "title": entry.title,
        "source_url": entry.url,
        "arc": entry.arc,
        "phase": entry.phase,
        "chapter": entry.chapter,
        "order": entry.order,
        "fetched_at": fetched_at,
        "content_hash": markdown_hash,
    }

    front_matter = yaml.safe_dump(
        metadata,
        sort_keys=False,
        allow_unicode=True,
    ).strip()

    text = f"---\n{front_matter}\n---\n\n{markdown_text}"
    abs_path.write_text(text, encoding="utf-8")
    return rel_path.as_posix()


def save_manifest(entries: list[dict[str, Any]]) -> None:
    ensure_data_dirs()
    save_json(
        MANIFEST_PATH,
        {
            "generated_at": now_iso(),
            "entries": entries,
        },
    )


def format_entry_for_manifest(entry: TocEntry, file_path: str, markdown_hash: str) -> dict[str, Any]:
    item = asdict(entry)
    item["key"] = entry.identity_key
    item["file_path"] = file_path
    item["content_hash"] = markdown_hash
    return item
