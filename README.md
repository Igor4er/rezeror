# Rezeror

Rezeror is a uv-based Python 3.14+ app that:

```
quick start
uv sync                          # installs all deps + dev (pytest)
uv run rezeror inspect-toc       # inspect TOC without downloading
uv run rezeror sync --arc 3      # sync one arc
uv run rezeror sync              # full sync (649 chapters)
uv run rezeror upload-content --base-url https://your-app.up.railway.app --username owner --password '***'
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

Upload local parsed content to remote server (owner auth required):

```bash
uv run rezeror upload-content \
	--base-url https://your-app.up.railway.app \
	--username owner \
	--password 'strong-password'
```

Include local progress DB in upload:

```bash
uv run rezeror upload-content \
	--base-url https://your-app.up.railway.app \
	--username owner \
	--password 'strong-password' \
	--include-progress
```

Status:

```bash
uv run rezeror status
```

Run web app:

```bash
uv run rezeror serve --host 127.0.0.1 --port 5000
```

## Docker

Build image:

```bash
docker build -t rezeror:latest .
```

Run container:

```bash
docker run --rm -p 8080:8080 \
	-e REZEROR_DATA_DIR=/data \
	-e REZEROR_DB_PATH=/data/progress.sqlite3 \
	-e REZEROR_OWNER_USERNAME=owner \
	-e REZEROR_OWNER_PASSWORD='change-me' \
	-e REZEROR_SESSION_SECRET='change-this' \
	-v rezeror_data:/data \
	rezeror:latest
```

The container runs as a non-root user and serves via Gunicorn on `0.0.0.0:8080`.

Railway note:

- If you mount a persistent volume and see `PermissionError: [Errno 13]` for paths under `/data`, it is usually a UID/GID mismatch between the container user and the mounted volume owner.
- This image runs as UID/GID `1000` by default (Railway-friendly).
- If your volume uses different ownership, rebuild with:

```bash
docker build --build-arg APP_UID=1000 --build-arg APP_GID=1000 -t rezeror:latest .
```

- Then set env vars consistently, for example:
	- `REZEROR_DATA_DIR=/data/c`
	- `REZEROR_DB_PATH=/data/progress.sqlite3`

## Environment Variables

You can override storage locations and owner auth with env vars:

- `REZEROR_DATA_DIR`: base data directory (default: `./data` under project root)
- `REZEROR_DB_PATH`: SQLite progress DB path (default: `<REZEROR_DATA_DIR>/progress.sqlite3`)
- `REZEROR_OWNER_USERNAME`: owner login username (default: `owner`)
- `REZEROR_OWNER_PASSWORD`: owner login password (required to enable owner-only writes)
- `REZEROR_SESSION_SECRET`: Flask session signing secret (set this in production)
- `REZEROR_OWNER_SESSION_DAYS`: owner login session lifetime in days (default: `3650`)

The app creates missing folders automatically for chapters/state and for the progress DB parent directory.

Example:

```bash
export REZEROR_DATA_DIR=/app/data
export REZEROR_DB_PATH=/app/state/progress.sqlite3
export REZEROR_OWNER_USERNAME=ihor
export REZEROR_OWNER_PASSWORD='strong-password'
export REZEROR_SESSION_SECRET='long-random-secret'
export REZEROR_OWNER_SESSION_DAYS=3650
```

## Owner-Protected API Routes

- `POST /owner/login` supports form submit and JSON body `{ "username": "...", "password": "..." }`
- `POST /owner/logout` supports both browser and JSON clients
- `POST /api/progress` is owner-only (public can still read via `GET /api/progress`)
- `POST /api/content/upload` is owner-only and accepts a ZIP archive in multipart form field `archive`
	- accepted paths inside ZIP:
		- `chapters/**/*.md`
		- `state/manifest.json`
		- `state/sync_state.json`
		- `progress.sqlite3` (optional)

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

