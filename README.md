# Rezeror

Rezeror is a uv-based Python 3.14+ app that:

```
quick start
uv sync                          # installs all deps + dev (pytest)
uv run rezeror inspect-toc       # inspect TOC without downloading
uv run rezeror sync --arc 3      # sync one arc
uv run rezeror sync              # full sync (649 chapters)
uv run rezeror status
uv run rezeror serve             # http://127.0.0.1:5000
uv run pytest 
```

- parses the live Re:Zero TOC from https://witchculttranslation.com/table-of-content/
- downloads chapter content incrementally
- stores chapters as markdown with front matter in `data/`
- serves a Flask + Jinja reading UI with server-side progress persistence

## Requirements

- `uv` installed
- Python 3.14+

## Setup

```bash
uv sync
```

## CLI Commands

Inspect TOC arc/phase/chapter counts (no chapter downloads):

```bash
uv run rezeror inspect-toc
```

Full sync:

```bash
uv run rezeror sync
```

Filtered sync (single arc):

```bash
uv run rezeror sync --arc 1
```

Force recheck chapter pages even if TOC hash is unchanged:

```bash
uv run rezeror sync --force-recheck
```

Status:

```bash
uv run rezeror status
```

Run web app:

```bash
uv run rezeror serve --host 127.0.0.1 --port 5000
```

## Environment Variables

You can override storage locations and owner auth with env vars:

- `REZEROR_DATA_DIR`: base data directory (default: `./data` under project root)
- `REZEROR_DB_PATH`: SQLite progress DB path (default: `<REZEROR_DATA_DIR>/progress.sqlite3`)
- `REZEROR_OWNER_USERNAME`: owner login username (default: `owner`)
- `REZEROR_OWNER_PASSWORD`: owner login password (required to enable owner-only writes)
- `REZEROR_SESSION_SECRET`: Flask session signing secret (set this in production)

The app creates missing folders automatically for chapters/state and for the progress DB parent directory.

Example:

```bash
export REZEROR_DATA_DIR=/app/data
export REZEROR_DB_PATH=/app/state/progress.sqlite3
export REZEROR_OWNER_USERNAME=ihor
export REZEROR_OWNER_PASSWORD='strong-password'
export REZEROR_SESSION_SECRET='long-random-secret'
```

## Owner-Protected API Routes

- `POST /owner/login` supports form submit and JSON body `{ "username": "...", "password": "..." }`
- `POST /owner/logout` supports both browser and JSON clients
- `POST /api/progress` is owner-only (public can still read via `GET /api/progress`)
- `POST /api/sync` is owner-only and supports:
	- `{}` for full sync
	- `{ "arc": 3 }` for one arc
	- `{ "force_recheck": true }` to force chapter checks

There is also a web login page at `/owner/login`.

You can also run the entry script directly:

```bash
uv run python main.py sync
```

## Project Layout

```
src/rezeror/
	parser/
		http.py        # retry/backoff HTTP client
		toc.py         # deterministic TOC state-machine parser
		chapters.py    # chapter extraction + HTML -> markdown conversion
		storage.py     # markdown/front matter writing, manifest/state JSON
		sync.py        # incremental sync orchestration
	web/
		app.py         # Flask app routes and reader rendering
		progress.py    # SQLite progress persistence
		templates/     # Jinja templates
		static/        # CSS/JS
	cli.py           # sync/status/serve/inspect-toc commands
```

## Parser Notes

- TOC parsing is grounded to `article#post-35 .entry-content`.
- Parsing is stream/state-machine based:
	- `h1` starting with `Arc ` sets current arc and resets phase.
	- `h1` starting with `Phase ` sets current phase.
	- each encountered `ul` while an arc is active contributes `li > a` chapters.
	- parsing stops at `h1` starting with `Side Content`.
- External links are included.
- Identity key is: `canonical_url + arc + phase + chapter`.

## Data Files (Gitignored)

Generated artifacts are all stored under `data/`:

- `data/chapters/**.md` chapter markdown files with YAML front matter
- `data/state/manifest.json` reader/library listing
- `data/state/sync_state.json` incremental sync state
- `data/progress.sqlite3` saved reader scroll positions

## Testing

Run fixture tests:

```bash
uv run pytest
```

