from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile


def validate_uploaded_json(target: Path, data: bytes, manifest_path: Path, sync_state_path: Path) -> None:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON payload for {target.name}") from exc

    if target == manifest_path:
        if not isinstance(payload, dict) or not isinstance(payload.get("entries", []), list):
            raise ValueError("manifest.json must be an object with an entries list")
        return

    if target == sync_state_path:
        if not isinstance(payload, dict) or not isinstance(payload.get("entries", {}), dict):
            raise ValueError("sync_state.json must be an object with an entries object")


def validate_uploaded_content(
    target: Path,
    data: bytes,
    manifest_path: Path,
    sync_state_path: Path,
    progress_db_path: Path,
) -> None:
    if target == manifest_path or target == sync_state_path:
        validate_uploaded_json(target, data, manifest_path, sync_state_path)
        return
    if target == progress_db_path:
        if not data.startswith(b"SQLite format 3\x00"):
            raise ValueError("progress.sqlite3 is not a valid sqlite3 file")
        return
    if target.suffix != ".md":
        raise ValueError("unsupported uploaded file type")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("chapter markdown files must be UTF-8 encoded") from exc


def write_bytes_atomically(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".upload.tmp")
    temp.write_bytes(data)
    temp.replace(target)


def safe_upload_target(
    member_name: str,
    chapters_dir: Path,
    manifest_path: Path,
    sync_state_path: Path,
    progress_db_path: Path,
) -> Path | None:
    if not member_name or "\x00" in member_name or "\\" in member_name:
        return None

    pure = Path(member_name)
    if pure.is_absolute() or ".." in pure.parts:
        return None

    normalized = pure.as_posix().lstrip("/")
    if normalized.startswith("/"):
        return None

    if normalized == "state/manifest.json":
        return manifest_path
    if normalized == "state/sync_state.json":
        return sync_state_path
    if normalized == "progress.sqlite3":
        return progress_db_path
    if normalized.startswith("chapters/") and normalized.endswith(".md"):
        rel = normalized[len("chapters/") :]
        chapter_target = chapters_dir / rel
        chapters_root = chapters_dir.resolve()
        chapter_resolved = chapter_target.resolve()
        if chapters_root not in chapter_resolved.parents and chapter_resolved != chapters_root:
            return None
        return chapter_target
    return None


def import_content_archive(
    archive_bytes: bytes,
    *,
    chapters_dir: Path,
    manifest_path: Path,
    sync_state_path: Path,
    progress_db_path: Path,
    max_archive_files: int,
    max_total_uncompressed_bytes: int,
    max_single_file_bytes: int,
) -> dict[str, int]:
    total_uncompressed = 0
    imported = 0
    skipped = 0
    pending_writes: list[tuple[Path, bytes]] = []

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
        infos = zf.infolist()
        if len(infos) > max_archive_files:
            raise ValueError("archive has too many files")

        for info in infos:
            if info.is_dir():
                continue

            if info.file_size > max_single_file_bytes:
                raise ValueError(f"archive member too large: {info.filename}")
            if info.compress_size > 0 and info.file_size / info.compress_size > 200:
                raise ValueError(f"archive member compression ratio is too high: {info.filename}")

            target = safe_upload_target(info.filename, chapters_dir, manifest_path, sync_state_path, progress_db_path)
            if target is None:
                skipped += 1
                continue

            total_uncompressed += info.file_size
            if total_uncompressed > max_total_uncompressed_bytes:
                raise ValueError("archive is too large")

            with zf.open(info, "r") as src:
                data = src.read(max_single_file_bytes + 1)
            if len(data) > max_single_file_bytes:
                raise ValueError(f"archive member too large after extraction: {info.filename}")

            validate_uploaded_content(target, data, manifest_path, sync_state_path, progress_db_path)
            pending_writes.append((target, data))

    for target, data in pending_writes:
        write_bytes_atomically(target, data)
        imported += 1

    return {
        "imported": imported,
        "skipped": skipped,
    }
