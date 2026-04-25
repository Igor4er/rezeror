from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path

import requests

from rezeror.config import MANIFEST_PATH, SYNC_STATE_PATH, ensure_data_dirs
from rezeror.parser.storage import load_json
from rezeror.parser.sync import inspect_toc, sync
from rezeror.web.app import create_app
from rezeror.web.progress import PROGRESS_DB_PATH, count_progress_rows


def _print_counts(counts: dict[str, dict[str, int]]) -> None:
    for arc, phases in counts.items():
        print(arc)
        for phase, count in phases.items():
            print(f"  {phase}: {count}")


def cmd_inspect_toc() -> int:
    entries, counts = inspect_toc()
    print(f"Entries: {len(entries)}")
    _print_counts(counts)
    return 0


def cmd_sync(arc: int | None, force_recheck: bool) -> int:
    result = sync(arc_filter=arc, force_recheck=force_recheck)
    print(json.dumps(result, indent=2))
    return 0


def cmd_status() -> int:
    ensure_data_dirs()
    manifest = load_json(MANIFEST_PATH, {"entries": []})
    state = load_json(SYNC_STATE_PATH, {"entries": {}, "last_sync_at": None})

    print(f"Manifest entries: {len(manifest.get('entries', []))}")
    print(f"State entries: {len(state.get('entries', {}))}")
    print(f"Last sync: {state.get('last_sync_at')}")
    print(f"Saved progress rows: {count_progress_rows()}")
    return 0


def cmd_serve(host: str, port: int, debug: bool) -> int:
    app = create_app()
    app.run(host=host, port=port, debug=debug)
    return 0


def _build_upload_archive(archive_path: Path, include_progress: bool) -> int:
    ensure_data_dirs()
    files_added = 0

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        chapters_root = MANIFEST_PATH.parent.parent / "chapters"
        if chapters_root.exists():
            for chapter_file in sorted(chapters_root.rglob("*.md")):
                zf.write(chapter_file, arcname=f"chapters/{chapter_file.relative_to(chapters_root).as_posix()}")
                files_added += 1

        if MANIFEST_PATH.exists():
            zf.write(MANIFEST_PATH, arcname="state/manifest.json")
            files_added += 1

        if SYNC_STATE_PATH.exists():
            zf.write(SYNC_STATE_PATH, arcname="state/sync_state.json")
            files_added += 1

        if include_progress and PROGRESS_DB_PATH.exists():
            zf.write(PROGRESS_DB_PATH, arcname="progress.sqlite3")
            files_added += 1

    return files_added


def cmd_upload_content(
    base_url: str,
    username: str,
    password: str,
    include_progress: bool,
    timeout: float,
) -> int:
    base = base_url.rstrip("/")

    with tempfile.TemporaryDirectory(prefix="rezeror-upload-") as td:
        archive_path = Path(td) / "content.zip"
        files_added = _build_upload_archive(archive_path, include_progress=include_progress)
        if files_added == 0:
            print("No local content found to upload.")
            return 1

        with requests.Session() as session:
            login_response = session.post(
                f"{base}/owner/login",
                json={"username": username, "password": password},
                timeout=timeout,
            )
            if login_response.status_code != 200:
                print(f"Login failed: {login_response.status_code} {login_response.text}")
                return 1

            with archive_path.open("rb") as fp:
                upload_response = session.post(
                    f"{base}/api/content/upload",
                    files={"archive": ("content.zip", fp, "application/zip")},
                    timeout=timeout,
                )

        if upload_response.status_code != 200:
            print(f"Upload failed: {upload_response.status_code} {upload_response.text}")
            return 1

        print(upload_response.text)
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rezeror")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_cmd = subparsers.add_parser("inspect-toc", help="Inspect TOC counts without downloading chapters")
    inspect_cmd.set_defaults(func=lambda args: cmd_inspect_toc())

    sync_cmd = subparsers.add_parser("sync", help="Sync chapters to local markdown")
    sync_cmd.add_argument("--arc", type=int, default=None, help="Filter to a single arc number")
    sync_cmd.add_argument(
        "--force-recheck",
        action="store_true",
        help="Force chapter re-fetch even when TOC hash is unchanged",
    )
    sync_cmd.set_defaults(func=lambda args: cmd_sync(args.arc, args.force_recheck))

    status_cmd = subparsers.add_parser("status", help="Show local parser/web state")
    status_cmd.set_defaults(func=lambda args: cmd_status())

    serve_cmd = subparsers.add_parser("serve", help="Start Flask reader app")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=5000)
    serve_cmd.add_argument("--debug", action="store_true")
    serve_cmd.set_defaults(func=lambda args: cmd_serve(args.host, args.port, args.debug))

    upload_cmd = subparsers.add_parser(
        "upload-content",
        help="Upload local chapters/state (and optionally progress DB) to a remote Rezeror server",
    )
    upload_cmd.add_argument("--base-url", required=True, help="Remote base URL, e.g. https://example.up.railway.app")
    upload_cmd.add_argument("--username", required=True, help="Owner username")
    upload_cmd.add_argument("--password", required=True, help="Owner password")
    upload_cmd.add_argument(
        "--include-progress",
        action="store_true",
        help="Include local progress.sqlite3 in the upload archive",
    )
    upload_cmd.add_argument("--timeout", type=float, default=30.0)
    upload_cmd.set_defaults(
        func=lambda args: cmd_upload_content(
            base_url=args.base_url,
            username=args.username,
            password=args.password,
            include_progress=args.include_progress,
            timeout=args.timeout,
        )
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
