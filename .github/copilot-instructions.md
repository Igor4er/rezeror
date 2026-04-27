# Copilot Instructions

## Commands

```bash
uv sync                          # install all deps including dev (pytest)
uv run pytest                    # run all tests
uv run pytest tests/test_toc_parser.py          # run a single test file
uv run pytest tests/test_toc_parser.py::test_toc_parser_state_machine_and_side_content_stop  # single test

uv run rezeror serve             # start Flask dev server on http://127.0.0.1:5000
uv run rezeror sync              # full chapter sync (requires network)
uv run rezeror sync --arc 3      # sync a single arc
uv run rezeror inspect-toc       # inspect TOC without downloading chapters
uv run rezeror status            # show sync status
```

> `test_reader_credit_skip.py` requires real chapter files under `data/chapters/` — it is an integration-level test that should only be run after `uv run rezeror sync`.

## Architecture

```
src/rezeror/
  config.py          # all env-var driven config; centralised path constants
  cli.py             # CLI entrypoint (sync / status / serve / inspect-toc / upload-content)
  parser/
    models.py        # TocEntry (dataclass, slots=True), SyncSummary
    http.py          # retry/backoff HTTP client
    toc.py           # state-machine TOC parser (grounded to article#post-35 .entry-content)
    chapters.py      # HTML → markdown conversion via markdownify
    storage.py       # markdown + YAML front-matter writing; manifest.json / sync_state.json
    sync.py          # incremental sync orchestration
  web/
    app.py           # Flask app; create_app() factory; all routes defined here
    progress.py      # SQLite reader scroll-position persistence
    templates/       # Jinja2 templates
    static/          # CSS / JS
    wsgi.py          # Gunicorn entrypoint
```

Data files are **gitignored** and live under `data/`:
- `data/chapters/**/*.md` — chapter markdown with YAML front matter
- `data/state/manifest.json` — reader/library listing
- `data/state/sync_state.json` — incremental sync state (hash + timestamps)
- `data/progress.sqlite3` — reader scroll positions

## Key Conventions

**Config** — all runtime paths and credentials are read from `REZEROR_*` env vars via `src/rezeror/config.py`. Module-level constants (`CHAPTERS_DIR`, `MANIFEST_PATH`, `PROGRESS_DB_PATH`, …) are imported directly into `web/app.py` and `web/progress.py`; tests override them with `monkeypatch.setattr`.

**Data models** — use `@dataclass(slots=True)` (see `parser/models.py`). Chapter identity is `url|arc|phase|chapter` (the `TocEntry.identity_key` property).

**TOC parser** — state-machine: `h1 "Arc …"` sets arc + resets phase; `h1 "Phase …"` sets phase; each `ul` while arc is active contributes chapters; parsing stops at `h1 "Side Content"`.

**Security** — all owner-only `POST` routes require `X-CSRF-Token` header matching the value returned at login. Rate limiting (`LOGIN_MAX_ATTEMPTS = 8` per `LOGIN_WINDOW_SECONDS = 900 s`) is enforced in `_login_attempts` (dict keyed by IP). Login is blocked for certain `Accept-Language` primary subtags. HTML is sanitised with `nh3` before rendering.

**HTML → Markdown** — conversion uses `markdownify`; rendered markdown goes through `nh3` allow-list sanitisation before being sent to the browser. Images are allowed only for `http`/`https` src schemes.

**Package manager** — `uv` only; do not use `pip` directly. Python ≥ 3.14 required. Use `from __future__ import annotations` at the top of every source file.

**Flask app** — created via `create_app()` factory in `web/app.py`. Tests use `flask_app.config.update(TESTING=True)` and `app.test_client()`. No blueprint split — all routes live in `app.py`.
