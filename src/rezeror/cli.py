from __future__ import annotations

import argparse
import json
from pathlib import Path

from rezeror.config import MANIFEST_PATH, SYNC_STATE_PATH, ensure_data_dirs
from rezeror.parser.storage import load_json
from rezeror.parser.sync import inspect_toc, sync
from rezeror.web.app import create_app
from rezeror.web.progress import count_progress_rows


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

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
