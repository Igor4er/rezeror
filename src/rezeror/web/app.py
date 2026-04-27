from __future__ import annotations

from datetime import timedelta
import secrets
import time
from typing import Any
from urllib.parse import urlsplit
import zipfile
import hmac
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from flask import Response
from flask.typing import ResponseReturnValue
from werkzeug.security import check_password_hash

from rezeror.config import (
    CHAPTERS_DIR,
    MANIFEST_PATH,
    PROGRESS_DB_PATH,
    SYNC_STATE_PATH,
    ensure_data_dirs,
    owner_auth_enabled,
    owner_credentials,
    owner_password_hash,
    owner_session_days,
    session_secret,
)
from rezeror.web.content import (
    adjacent_entries,
    format_chapter_display_title,
    group_entries,
    load_manifest_entries,
    read_markdown_with_front_matter,
    render_markdown_with_toc,
    safe_chapter_abs_path,
)
from rezeror.web.progress import (
    get_last_read_chapter_path,
    get_progress,
    has_progress,
    init_progress_db,
    save_progress,
)
from rezeror.web.uploads import import_content_archive


MAX_UPLOAD_ARCHIVE_BYTES = 120_000_000
MAX_TOTAL_UNCOMPRESSED_BYTES = 150_000_000
MAX_SINGLE_FILE_BYTES = 25_000_000
MAX_ARCHIVE_FILES = 5_000
MAX_SCROLL_Y = 10_000_000

LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_ATTEMPTS = 8

_login_attempts: dict[str, list[float]] = {}

CSRF_TOKEN_KEY = "owner_csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
BLOCKED_LANGUAGE_PRIMARY_SUBTAG = "ur"[::-1]


def _format_chapter_display_title(metadata: dict[str, Any], fallback: str) -> str:
    return format_chapter_display_title(metadata, fallback)


def _load_manifest_entries() -> list[dict[str, Any]]:
    return load_manifest_entries(MANIFEST_PATH)


def _safe_chapter_abs_path(chapter_path: str):
    return safe_chapter_abs_path(chapter_path, CHAPTERS_DIR)


def _read_markdown_with_front_matter(chapter_path: str) -> tuple[dict[str, Any], str]:
    return read_markdown_with_front_matter(chapter_path, CHAPTERS_DIR)


def _render_markdown_with_toc(markdown_text: str) -> tuple[str, list[dict[str, str]]]:
    return render_markdown_with_toc(markdown_text)


def _adjacent_entries(chapter_path: str, entries: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    return adjacent_entries(chapter_path, entries)


def _group_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return group_entries(entries)


def _owner_logged_in() -> bool:
    return session.get("is_owner") is True


def _owner_progress_state(chapter_path: str) -> tuple[int, bool]:
    if not _owner_logged_in():
        return 0, False
    return get_progress(chapter_path), has_progress(chapter_path)


def _json_error(message: str, status: int) -> ResponseReturnValue:
    return jsonify({"error": message}), status


def _require_owner_json() -> ResponseReturnValue | None:
    if not owner_auth_enabled():
        return _json_error("owner authentication is not configured", 503)
    if not _owner_logged_in():
        return _json_error("owner authentication required", 403)
    return None


def _client_addr() -> str:
    forwarded = request.headers.get("X-Real-IP", request.headers.get("X-Forwarded-For", "unknown"))
    return forwarded.split(",", 1)[0].strip()


def _is_login_allowed(username: str) -> bool:
    now = time.time()
    key = f"{_client_addr()}:{username.lower()}"
    attempts = [ts for ts in _login_attempts.get(key, []) if now - ts <= LOGIN_WINDOW_SECONDS]
    _login_attempts[key] = attempts
    return len(attempts) < LOGIN_MAX_ATTEMPTS


def _record_login_failure(username: str) -> None:
    now = time.time()
    key = f"{_client_addr()}:{username.lower()}"
    attempts = [ts for ts in _login_attempts.get(key, []) if now - ts <= LOGIN_WINDOW_SECONDS]
    attempts.append(now)
    _login_attempts[key] = attempts


def _clear_login_failures(username: str) -> None:
    key = f"{_client_addr()}:{username.lower()}"
    _login_attempts.pop(key, None)


def _get_or_create_csrf_token() -> str:
    token = session.get(CSRF_TOKEN_KEY)
    if isinstance(token, str) and token:
        return token
    token = secrets.token_urlsafe(32)
    session[CSRF_TOKEN_KEY] = token
    return token


def _require_csrf() -> ResponseReturnValue | None:
    expected = session.get(CSRF_TOKEN_KEY)
    if not isinstance(expected, str) or not expected:
        return _json_error("csrf token is missing", 403)

    provided = request.headers.get(CSRF_HEADER_NAME)
    if not provided:
        provided = request.form.get("csrf_token")
    if not isinstance(provided, str) or not hmac.compare_digest(provided, expected):
        return _json_error("csrf token is invalid", 403)
    return None


def _wants_json_response() -> bool:
    if request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json"


def _request_uses_blocked_language() -> bool:
    accept_language = request.headers.get("Accept-Language", "")
    for entry in accept_language.split(","):
        language_range = entry.split(";", 1)[0].strip()
        if not language_range:
            continue
        primary_subtag = language_range.split("-", 1)[0].split("_", 1)[0].strip().lower()
        if primary_subtag == BLOCKED_LANGUAGE_PRIMARY_SUBTAG:
            return True
    return False


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
    return render_template(
        "owner_login.html",
        next_path=next_path,
        error=message,
        csrf_token=_get_or_create_csrf_token(),
    ), status


def _owner_login_success(next_path: str) -> ResponseReturnValue:
    token = _get_or_create_csrf_token()
    if _wants_json_response():
        return jsonify({"ok": True, "csrf_token": token})
    return redirect(next_path)


def _owner_password_matches(submitted_password: str) -> bool:
    _, expected_password = owner_credentials()
    expected_hash = owner_password_hash().strip()

    if expected_hash:
        try:
            return check_password_hash(expected_hash, submitted_password)
        except ValueError:
            return False

    if not expected_password:
        return False
    return hmac.compare_digest(expected_password, submitted_password)


def _import_content_archive(archive_bytes: bytes) -> dict[str, int]:
    return import_content_archive(
        archive_bytes,
        chapters_dir=CHAPTERS_DIR,
        manifest_path=MANIFEST_PATH,
        sync_state_path=SYNC_STATE_PATH,
        progress_db_path=PROGRESS_DB_PATH,
        max_archive_files=MAX_ARCHIVE_FILES,
        max_total_uncompressed_bytes=MAX_TOTAL_UNCOMPRESSED_BYTES,
        max_single_file_bytes=MAX_SINGLE_FILE_BYTES,
    )


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
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_ARCHIVE_BYTES
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; base-uri 'self'; frame-ancestors 'none'",
        )
        return response

    @app.before_request
    def block_disallowed_languages() -> ResponseReturnValue | None:
        if not _request_uses_blocked_language():
            return None
        if _wants_json_response():
            return _json_error("forbidden language preference", 403)
        abort(403)

    @app.context_processor
    def inject_template_security_values() -> dict[str, Any]:
        token = session.get(CSRF_TOKEN_KEY)
        if _owner_logged_in():
            token = _get_or_create_csrf_token()
        return {"owner_csrf_token": token or ""}

    @app.get("/")
    @app.get("/library")
    def library() -> str:
        entries = _load_manifest_entries()
        grouped_entries = _group_entries(entries)
        owner_authenticated = _owner_logged_in()
        last_read_chapter_path = get_last_read_chapter_path() if owner_authenticated else None
        last_read_entry = None
        if last_read_chapter_path:
            last_read_entry = next(
                (entry for entry in entries if entry.get("file_path") == last_read_chapter_path),
                None,
            )
        return render_template(
            "library.html",
            entries=entries,
            grouped_entries=grouped_entries,
            owner_authenticated=owner_authenticated,
            last_read_chapter_path=last_read_chapter_path,
            last_read_entry=last_read_entry,
        )

    @app.get("/healthz")
    def healthz() -> ResponseReturnValue:
        return jsonify({"status": "ok"}), 200

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return app.send_static_file("favicon.ico")

    @app.get("/read/<path:chapter_path>")
    def read_chapter(chapter_path: str) -> str:
        entries = _load_manifest_entries()
        try:
            metadata, markdown_text = _read_markdown_with_front_matter(chapter_path)
        except (FileNotFoundError, ValueError):
            abort(404)

        html, _ = _render_markdown_with_toc(markdown_text)
        prev_entry, next_entry = _adjacent_entries(chapter_path, entries)
        saved_scroll, has_saved_progress = _owner_progress_state(chapter_path)
        chapter_display_title = _format_chapter_display_title(metadata, chapter_path)

        return render_template(
            "reader.html",
            chapter_path=chapter_path,
            metadata=metadata,
            chapter_display_title=chapter_display_title,
            html=html,
            prev_entry=prev_entry,
            next_entry=next_entry,
            saved_scroll=saved_scroll,
            has_saved_progress=has_saved_progress,
            owner_authenticated=_owner_logged_in(),
        )

    @app.get("/owner/login")
    def owner_login_form() -> ResponseReturnValue:
        next_path = _safe_next_path(request.args.get("next"))
        if _owner_logged_in():
            return redirect(next_path)
        return render_template(
            "owner_login.html",
            next_path=next_path,
            error=None,
            csrf_token=_get_or_create_csrf_token(),
        )

    @app.post("/owner/login")
    def owner_login_submit() -> ResponseReturnValue:
        username, password, next_path = _extract_owner_login_payload()

        if not request.is_json:
            csrf_error = _require_csrf()
            if csrf_error:
                return _owner_login_failure("invalid csrf token", 403, next_path)

        if not owner_auth_enabled():
            return _owner_login_failure("owner authentication is not configured", 503, next_path)

        if not _is_login_allowed(username):
            return _owner_login_failure("too many attempts, try again later", 429, next_path)

        expected_username, _ = owner_credentials()
        if username == expected_username and _owner_password_matches(password):
            session.permanent = True
            session["is_owner"] = True
            _clear_login_failures(username)
            return _owner_login_success(next_path)

        _record_login_failure(username)
        return _owner_login_failure("invalid credentials", 403, next_path)

    @app.post("/owner/logout")
    def owner_logout() -> ResponseReturnValue:
        csrf_error = _require_csrf()
        if csrf_error:
            return csrf_error
        session.pop("is_owner", None)
        session.pop(CSRF_TOKEN_KEY, None)
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
        scroll_y, has_saved_progress = _owner_progress_state(chapter_path)
        return jsonify(
            {
                "chapter_path": chapter_path,
                "scroll_y": scroll_y,
                "has_saved_progress": has_saved_progress,
            }
        )

    @app.post("/api/progress")
    def api_progress_save():
        auth_error = _require_owner_json()
        if auth_error:
            return auth_error

        csrf_error = _require_csrf()
        if csrf_error:
            return csrf_error

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
        if scroll_int > MAX_SCROLL_Y:
            return jsonify({"error": "scroll_y exceeds maximum allowed value"}), 400

        save_progress(chapter_path, scroll_int)
        return jsonify({"ok": True})

    @app.post("/api/content/upload")
    def api_content_upload():
        auth_error = _require_owner_json()
        if auth_error:
            return auth_error

        csrf_error = _require_csrf()
        if csrf_error:
            return csrf_error

        upload_file = request.files.get("archive")
        if upload_file is not None:
            archive_bytes = upload_file.read()
        else:
            archive_bytes = request.get_data(cache=False)

        if not archive_bytes:
            return _json_error("archive file is required", 400)

        try:
            result = _import_content_archive(archive_bytes)
        except zipfile.BadZipFile:
            return _json_error("invalid zip archive", 400)
        except ValueError as exc:
            return _json_error(str(exc), 400)

        return jsonify({"ok": True, **result})

    return app
