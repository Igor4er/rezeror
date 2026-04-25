from __future__ import annotations

import io
from pathlib import Path
import zipfile

import pytest

from rezeror.web import app as web_app
from rezeror.web import progress as web_progress


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    chapters_dir = data_dir / "chapters"
    state_dir = data_dir / "state"
    manifest_path = state_dir / "manifest.json"
    sync_state_path = state_dir / "sync_state.json"
    db_path = tmp_path / "nested" / "state" / "progress.sqlite3"

    def ensure_data_dirs() -> None:
        chapters_dir.mkdir(parents=True, exist_ok=True)
        state_dir.mkdir(parents=True, exist_ok=True)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(web_app, "CHAPTERS_DIR", chapters_dir)
    monkeypatch.setattr(web_app, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(web_app, "SYNC_STATE_PATH", sync_state_path)
    monkeypatch.setattr(web_app, "PROGRESS_DB_PATH", db_path)
    monkeypatch.setattr(web_app, "ensure_data_dirs", ensure_data_dirs)

    monkeypatch.setattr(web_progress, "PROGRESS_DB_PATH", db_path)
    monkeypatch.setattr(web_progress, "ensure_data_dirs", ensure_data_dirs)

    monkeypatch.setenv("REZEROR_OWNER_USERNAME", "owner")
    monkeypatch.setenv("REZEROR_OWNER_PASSWORD", "secret")
    monkeypatch.setenv("REZEROR_SESSION_SECRET", "test-secret-with-at-least-32-characters")

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
    csrf_token = login.get_json()["csrf_token"]

    blocked_missing_csrf = client.post("/api/progress", json=payload)
    assert blocked_missing_csrf.status_code == 403

    allowed = client.post("/api/progress", json=payload, headers={"X-CSRF-Token": csrf_token})
    assert allowed.status_code == 200
    assert allowed.get_json() == {"ok": True}

    read_back = client.get("/api/progress", query_string={"chapter_path": payload["chapter_path"]})
    body = read_back.get_json()
    assert body["scroll_y"] == 120
    assert body["has_saved_progress"] is True


def test_owner_login_blocks_disallowed_accept_language(app):
    client = app.test_client()

    response = client.post(
        "/owner/login",
        json={"username": "owner", "password": "secret"},
        headers={"Accept-Language": f'{"ur"[::-1]}-UA,en;q=0.8'},
    )

    assert response.status_code == 403
    assert response.get_json() == {"error": "forbidden language preference"}


def test_content_upload_requires_owner_login_and_imports_chapters_and_state(app):
    client = app.test_client()

    def make_archive() -> io.BytesIO:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("chapters/arc-1/chapter-1.md", "# Chapter 1\n")
            zf.writestr("state/manifest.json", '{"entries": []}')
            zf.writestr("state/sync_state.json", '{"entries": {}, "last_toc_hash": "", "last_sync_at": null}')
        archive.seek(0)
        return archive

    blocked = client.post(
        "/api/content/upload",
        data={"archive": (make_archive(), "content.zip")},
        content_type="multipart/form-data",
    )
    assert blocked.status_code == 403

    login = client.post("/owner/login", json={"username": "owner", "password": "secret"})
    assert login.status_code == 200
    csrf_token = login.get_json()["csrf_token"]

    allowed = client.post(
        "/api/content/upload",
        data={"archive": (make_archive(), "content.zip")},
        headers={"X-CSRF-Token": csrf_token},
        content_type="multipart/form-data",
    )
    assert allowed.status_code == 200

    body = allowed.get_json()
    assert body["ok"] is True
    assert body["imported"] == 3

    chapter_path = web_app.CHAPTERS_DIR / "arc-1" / "chapter-1.md"
    assert chapter_path.exists()
    assert web_app.MANIFEST_PATH.exists()
    assert web_app.SYNC_STATE_PATH.exists()


def test_content_upload_rejects_invalid_manifest_payload(app):
    client = app.test_client()
    login = client.post("/owner/login", json={"username": "owner", "password": "secret"})
    assert login.status_code == 200
    csrf_token = login.get_json()["csrf_token"]

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("state/manifest.json", "not-json")
    archive.seek(0)

    response = client.post(
        "/api/content/upload",
        data={"archive": (archive, "content.zip")},
        headers={"X-CSRF-Token": csrf_token},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "invalid JSON" in response.get_json()["error"]


def test_owner_logout_requires_csrf(app):
    client = app.test_client()
    login = client.post("/owner/login", json={"username": "owner", "password": "secret"})
    assert login.status_code == 200
    csrf_token = login.get_json()["csrf_token"]

    blocked = client.post("/owner/logout")
    assert blocked.status_code == 403

    allowed = client.post("/owner/logout", headers={"X-CSRF-Token": csrf_token})
    assert allowed.status_code == 302
