from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
import hmac
import markdown
import yaml
from bs4 import BeautifulSoup
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from hashlib import sha256

from rezeror.config import (
    CHAPTERS_DIR,
    MANIFEST_PATH,
    ensure_data_dirs,
    owner_auth_enabled,
    owner_credentials,
    owner_session_days,
    session_secret,
)
from rezeror.parser.storage import load_json
from rezeror.parser.sync import sync
from rezeror.web.progress import get_progress, has_progress, init_progress_db, save_progress


def _load_manifest_entries() -> list[dict[str, Any]]:
    manifest = load_json(MANIFEST_PATH, {"entries": []})
    return manifest.get("entries", [])


def _safe_chapter_abs_path(chapter_path: str) -> Path:
    candidate = (CHAPTERS_DIR / chapter_path).resolve()
    chapters_root = CHAPTERS_DIR.resolve()
    if chapters_root not in candidate.parents and candidate != chapters_root:
        raise ValueError("Invalid chapter path")
    return candidate


def _read_markdown_with_front_matter(chapter_path: str) -> tuple[dict[str, Any], str]:
    abs_path = _safe_chapter_abs_path(chapter_path)
    if not abs_path.exists():
        raise FileNotFoundError(chapter_path)

    text = abs_path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        parts = text.split("\n---\n", 1)
        if len(parts) == 2:
            front_matter_text = parts[0][4:]
            body = parts[1].lstrip("\n")
            metadata = yaml.safe_load(front_matter_text) or {}
            return metadata, body
    return {}, text


def _render_markdown_with_toc(markdown_text: str) -> tuple[str, list[dict[str, str]]]:
    md = markdown.Markdown(extensions=["toc", "fenced_code", "tables"])
    html = md.convert(markdown_text)

    soup = BeautifulSoup(html, "html.parser")
    toc_items: list[dict[str, str]] = []
    for heading in soup.select("h1[id], h2[id], h3[id], h4[id], h5[id], h6[id]"):
        heading_id = heading.get("id", "")
        if not isinstance(heading_id, str):
            heading_id = ""
        heading_level = str(heading.name or "")
        toc_items.append(
            {
                "id": heading_id,
                "level": heading_level,
                "text": heading.get_text(" ", strip=True),
            }
        )
    return html, toc_items


def _adjacent_entries(chapter_path: str, entries: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    index = next((i for i, item in enumerate(entries) if item.get("file_path") == chapter_path), None)
    if index is None:
        return None, None

    prev_entry = entries[index - 1] if index > 0 else None
    next_entry = entries[index + 1] if index < len(entries) - 1 else None
    return prev_entry, next_entry


def _group_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for entry in entries:
        arc = entry.get("arc") or "Unknown Arc"
        phase = entry.get("phase") or "Main"
        arc_bucket = grouped.setdefault(arc, {})
        phase_bucket = arc_bucket.setdefault(phase, [])
        phase_bucket.append(entry)

    grouped_list: list[dict[str, Any]] = []
    for arc, phases in grouped.items():
        phase_groups = [{"phase": phase, "entries": phase_entries} for phase, phase_entries in phases.items()]
        grouped_list.append(
            {
                "arc": arc,
                "phases": phase_groups,
                "count": sum(len(group["entries"]) for group in phase_groups),
            }
        )
    return grouped_list


def _owner_logged_in() -> bool:
    return session.get("is_owner") is True


def _json_error(message: str, status: int) -> ResponseReturnValue:
    return jsonify({"error": message}), status


def _require_owner_json() -> ResponseReturnValue | None:
    if not owner_auth_enabled():
        return _json_error("owner authentication is not configured", 503)
    if not _owner_logged_in():
        return _json_error("owner authentication required", 403)
    return None


def _wants_json_response() -> bool:
    if request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json"


def _safe_next_path(raw_next: str | None) -> str:
    if not raw_next:
        return url_for("library")
    parsed = urlsplit(raw_next)
    # Allow only local app-relative redirects.
    if parsed.scheme or parsed.netloc:
        return url_for("library")
    if not raw_next.startswith("/"):
        return url_for("library")
    return raw_next


def _extract_owner_login_payload() -> tuple[str, str, str]:
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        next_path = _safe_next_path(payload.get("next"))
        return username, password, next_path

    form = request.form
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    next_path = _safe_next_path(form.get("next"))
    return username, password, next_path


def _owner_login_failure(message: str, status: int, next_path: str) -> ResponseReturnValue:
    if _wants_json_response():
        return _json_error(message, status)
    return render_template("owner_login.html", next_path=next_path, error=message), status


def _owner_login_success(next_path: str) -> ResponseReturnValue:
    if _wants_json_response():
        return jsonify({"ok": True})
    return redirect(next_path)


def create_app() -> Flask:
    ensure_data_dirs()
    init_progress_db()

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = session_secret()
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=owner_session_days())

    @app.get("/")
    @app.get("/library")
    def library() -> str:
        entries = _load_manifest_entries()
        grouped_entries = _group_entries(entries)
        return render_template("library.html", entries=entries, grouped_entries=grouped_entries)

    @app.get("/read/<path:chapter_path>")
    def read_chapter(chapter_path: str) -> str:
        entries = _load_manifest_entries()
        try:
            metadata, markdown_text = _read_markdown_with_front_matter(chapter_path)
        except (FileNotFoundError, ValueError):
            abort(404)

        html, _ = _render_markdown_with_toc(markdown_text)
        prev_entry, next_entry = _adjacent_entries(chapter_path, entries)
        saved_scroll = get_progress(chapter_path)
        has_saved_progress = has_progress(chapter_path)

        return render_template(
            "reader.html",
            chapter_path=chapter_path,
            metadata=metadata,
            html=html,
            prev_entry=prev_entry,
            next_entry=next_entry,
            saved_scroll=saved_scroll,
            has_saved_progress=has_saved_progress,
        )

    @app.get("/read/<path:chapter_path>/toc")
    def chapter_toc(chapter_path: str) -> str:
        entries = _load_manifest_entries()
        try:
            metadata, markdown_text = _read_markdown_with_front_matter(chapter_path)
        except (FileNotFoundError, ValueError):
            abort(404)

        _, toc_items = _render_markdown_with_toc(markdown_text)
        prev_entry, next_entry = _adjacent_entries(chapter_path, entries)

        current_index = next((i for i, item in enumerate(entries) if item.get("file_path") == chapter_path), None)
        progress_info: dict[str, Any] | None = None
        if current_index is not None and entries:
            current_entry = entries[current_index]
            arc_name = current_entry.get("arc")
            phase_name = current_entry.get("phase")

            arc_entries = [item for item in entries if item.get("arc") == arc_name]
            phase_entries = [
                item
                for item in entries
                if item.get("arc") == arc_name and item.get("phase") == phase_name
            ]

            arc_index = next((i for i, item in enumerate(arc_entries) if item.get("file_path") == chapter_path), None)
            phase_index = next((i for i, item in enumerate(phase_entries) if item.get("file_path") == chapter_path), None)

            overall_position = current_index + 1
            overall_total = len(entries)
            progress_info = {
                "overall_position": overall_position,
                "overall_total": overall_total,
                "overall_percent": round((overall_position / overall_total) * 100) if overall_total else 0,
                "arc": arc_name,
                "arc_position": (arc_index + 1) if arc_index is not None else None,
                "arc_total": len(arc_entries),
                "phase": phase_name,
                "phase_position": (phase_index + 1) if phase_index is not None else None,
                "phase_total": len(phase_entries),
            }

        return render_template(
            "chapter_toc.html",
            chapter_path=chapter_path,
            metadata=metadata,
            toc_items=toc_items,
            prev_entry=prev_entry,
            next_entry=next_entry,
            progress_info=progress_info,
        )

    @app.get("/owner/login")
    def owner_login_form() -> ResponseReturnValue:
        next_path = _safe_next_path(request.args.get("next"))
        if _owner_logged_in():
            return redirect(next_path)
        return render_template("owner_login.html", next_path=next_path, error=None)

    @app.post("/owner/login")
    def owner_login_submit() -> ResponseReturnValue:
        username, password, next_path = _extract_owner_login_payload()

        if not owner_auth_enabled():
            return _owner_login_failure("owner authentication is not configured", 503, next_path)

        expected_username, expected_password = owner_credentials()
        if username == expected_username and hmac.compare_digest(sha256(expected_password.encode()).digest(), sha256(password.encode()).digest()):
            session.permanent = True
            session["is_owner"] = True
            return _owner_login_success(next_path)

        return _owner_login_failure("invalid credentials", 403, next_path)

    @app.post("/owner/logout")
    def owner_logout() -> ResponseReturnValue:
        session.pop("is_owner", None)
        if _wants_json_response():
            return jsonify({"ok": True})
        return redirect(url_for("library"))

    @app.get("/api/progress")
    def api_progress_get():
        chapter_path = request.args.get("chapter_path", "")
        if not chapter_path:
            return jsonify({"error": "chapter_path is required"}), 400
        try:
            _safe_chapter_abs_path(chapter_path)
        except ValueError:
            return jsonify({"error": "invalid chapter_path"}), 400
        return jsonify(
            {
                "chapter_path": chapter_path,
                "scroll_y": get_progress(chapter_path),
                "has_saved_progress": has_progress(chapter_path),
            }
        )

    @app.post("/api/progress")
    def api_progress_save():
        auth_error = _require_owner_json()
        if auth_error:
            return auth_error

        payload = request.get_json(silent=True) or {}
        chapter_path = payload.get("chapter_path", "")
        scroll_y = payload.get("scroll_y", 0)

        if not chapter_path:
            return jsonify({"error": "chapter_path is required"}), 400
        try:
            _safe_chapter_abs_path(chapter_path)
        except ValueError:
            return jsonify({"error": "invalid chapter_path"}), 400

        try:
            scroll_int = max(0, int(scroll_y))
        except (TypeError, ValueError):
            return jsonify({"error": "scroll_y must be an integer"}), 400

        save_progress(chapter_path, scroll_int)
        return jsonify({"ok": True})

    @app.post("/api/sync")
    def api_sync():
        auth_error = _require_owner_json()
        if auth_error:
            return auth_error

        payload = request.get_json(silent=True) or {}
        arc = payload.get("arc")
        force_recheck = bool(payload.get("force_recheck", False))

        if arc in (None, ""):
            arc_filter = None
        else:
            try:
                arc_filter = int(arc)
            except (TypeError, ValueError):
                return _json_error("arc must be an integer", 400)
            if arc_filter <= 0:
                return _json_error("arc must be positive", 400)

        result = sync(arc_filter=arc_filter, force_recheck=force_recheck)
        return jsonify(result)

    return app
