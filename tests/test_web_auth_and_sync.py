from __future__ import annotations

from pathlib import Path

import pytest

from rezeror.web import app as web_app
from rezeror.web import progress as web_progress


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    chapters_dir = data_dir / "chapters"
    state_dir = data_dir / "state"
    manifest_path = state_dir / "manifest.json"
    db_path = tmp_path / "nested" / "state" / "progress.sqlite3"

    def ensure_data_dirs() -> None:
        chapters_dir.mkdir(parents=True, exist_ok=True)
        state_dir.mkdir(parents=True, exist_ok=True)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(web_app, "CHAPTERS_DIR", chapters_dir)
    monkeypatch.setattr(web_app, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(web_app, "ensure_data_dirs", ensure_data_dirs)

    monkeypatch.setattr(web_progress, "PROGRESS_DB_PATH", db_path)
    monkeypatch.setattr(web_progress, "ensure_data_dirs", ensure_data_dirs)

    monkeypatch.setenv("REZEROR_OWNER_USERNAME", "owner")
    monkeypatch.setenv("REZEROR_OWNER_PASSWORD", "secret")
    monkeypatch.setenv("REZEROR_SESSION_SECRET", "test-secret")

    flask_app = web_app.create_app()
    flask_app.config.update(TESTING=True)
    return flask_app


def test_progress_write_requires_owner_login(app):
    client = app.test_client()
    payload = {
        "chapter_path": "arc-1-a-tumultuous-first-day/chapter-1.md",
        "scroll_y": 120,
    }

    blocked = client.post("/api/progress", json=payload)
    assert blocked.status_code == 403

    login = client.post("/owner/login", json={"username": "owner", "password": "secret"})
    assert login.status_code == 200

    allowed = client.post("/api/progress", json=payload)
    assert allowed.status_code == 200
    assert allowed.get_json() == {"ok": True}

    read_back = client.get("/api/progress", query_string={"chapter_path": payload["chapter_path"]})
    body = read_back.get_json()
    assert body["scroll_y"] == 120
    assert body["has_saved_progress"] is True


def test_sync_endpoint_requires_owner_login_and_runs_when_authenticated(app, monkeypatch: pytest.MonkeyPatch):
    client = app.test_client()

    called: dict[str, object] = {}

    def fake_sync(arc_filter=None, force_recheck=False):
        called["arc_filter"] = arc_filter
        called["force_recheck"] = force_recheck
        return {
            "summary": {"total": 1, "new": 1, "updated": 0, "skipped": 0, "errors": 0},
            "counts": {"Arc 1": {"Main": 1}},
            "entries": 1,
        }

    monkeypatch.setattr(web_app, "sync", fake_sync)

    blocked = client.post("/api/sync", json={})
    assert blocked.status_code == 403

    login = client.post("/owner/login", json={"username": "owner", "password": "secret"})
    assert login.status_code == 200

    allowed = client.post("/api/sync", json={"arc": 1, "force_recheck": True})
    assert allowed.status_code == 200

    body = allowed.get_json()
    assert body["entries"] == 1
    assert called == {"arc_filter": 1, "force_recheck": True}
