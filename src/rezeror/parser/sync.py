from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Optional

from rezeror.config import TOC_URL, ensure_data_dirs
from rezeror.parser.chapters import content_hash, extract_chapter_content_html, html_fragment_to_markdown
from rezeror.parser.http import HttpClient
from rezeror.parser.models import SyncSummary, TocEntry
from rezeror.parser.storage import (
    format_entry_for_manifest,
    load_state,
    now_iso,
    save_manifest,
    save_state,
    write_markdown_chapter,
)
from rezeror.parser.toc import build_arc_phase_counts, parse_toc_entries, toc_hash


def _is_pdf_url(url: str) -> bool:
    from urllib.parse import urlsplit
    path = urlsplit(url).path.lower()
    return path.endswith(".pdf")


def _pdf_stub_markdown(entry: TocEntry) -> str:
    return (
        f"# {entry.title}\n\n"
        f"This chapter is distributed as a PDF document.\n\n"
        f"[Open PDF]({entry.url})\n"
    )


def _arc_matches(entry: TocEntry, arc_filter: Optional[int]) -> bool:
    if arc_filter is None:
        return True
    arc_lower = entry.arc.lower()
    prefix = f"arc {arc_filter}"
    if not arc_lower.startswith(prefix):
        return False
    # Ensure the next char is not a digit (avoids arc 1 matching arc 10, arc 11, etc.)
    rest = arc_lower[len(prefix):]
    return not rest or not rest[0].isdigit()


def inspect_toc(http_client: Optional[HttpClient] = None) -> tuple[list[TocEntry], dict[str, dict[str, int]]]:
    client = http_client or HttpClient()
    response = client.fetch_text(TOC_URL)
    entries = parse_toc_entries(response.text, TOC_URL)
    counts = build_arc_phase_counts(entries)
    return entries, counts


def sync(
    arc_filter: Optional[int] = None,
    force_recheck: bool = False,
    http_client: Optional[HttpClient] = None,
) -> dict[str, Any]:
    ensure_data_dirs()
    client = http_client or HttpClient()
    state = load_state()

    toc_response = client.fetch_text(TOC_URL)
    all_entries = parse_toc_entries(toc_response.text, TOC_URL)
    filtered_entries = [entry for entry in all_entries if _arc_matches(entry, arc_filter)]

    counts = build_arc_phase_counts(filtered_entries)
    current_toc_hash = toc_hash(filtered_entries)
    known_entries = state.get("entries", {})

    summary = SyncSummary(total=len(filtered_entries))
    manifest_entries: list[dict[str, Any]] = []

    toc_unchanged = state.get("last_toc_hash") == current_toc_hash

    for entry in filtered_entries:
        key = entry.identity_key
        known = known_entries.get(key)

        # If TOC did not change, trust prior content hash and skip chapter fetches.
        if known and toc_unchanged and not force_recheck:
            summary.skipped += 1
            manifest_entries.append(
                {
                    **asdict(entry),
                    "key": key,
                    "file_path": known["file_path"],
                    "content_hash": known["content_hash"],
                }
            )
            continue

        request_headers: dict[str, str] = {}
        if known and known.get("etag"):
            request_headers["If-None-Match"] = known["etag"]
        if known and known.get("last_modified"):
            request_headers["If-Modified-Since"] = known["last_modified"]

        try:
            # PDF URLs: skip HTML fetch, generate a stub markdown with a link
            if _is_pdf_url(entry.url):
                markdown_text = _pdf_stub_markdown(entry)
                markdown_hash = content_hash(markdown_text)
                if known and known.get("content_hash") == markdown_hash:
                    summary.skipped += 1
                    manifest_entries.append(
                        {
                            **asdict(entry),
                            "key": key,
                            "file_path": known["file_path"],
                            "content_hash": markdown_hash,
                        }
                    )
                    continue
                fetched_at = datetime.now(UTC).isoformat()
                file_path = write_markdown_chapter(entry, markdown_text, markdown_hash, fetched_at)
                known_entries[key] = {
                    "file_path": file_path,
                    "content_hash": markdown_hash,
                    "etag": None,
                    "last_modified": None,
                    "source_url": entry.url,
                    "updated_at": fetched_at,
                }
                if known:
                    summary.updated += 1
                else:
                    summary.new += 1
                manifest_entries.append(format_entry_for_manifest(entry, file_path, markdown_hash))
                continue

            chapter_response = client.fetch_text(
                entry.url,
                headers=request_headers or None,
                allow_not_modified=True,
            )
            if chapter_response.status_code == 304 and known:
                summary.skipped += 1
                manifest_entries.append(
                    {
                        **asdict(entry),
                        "key": key,
                        "file_path": known["file_path"],
                        "content_hash": known["content_hash"],
                    }
                )
                continue

            content_html = extract_chapter_content_html(chapter_response.text)
            markdown_text = html_fragment_to_markdown(content_html)
            markdown_hash = content_hash(markdown_text)

            if known and known.get("content_hash") == markdown_hash and known.get("file_path"):
                summary.skipped += 1
                known_entries[key] = {
                    **known,
                    "etag": chapter_response.headers.get("ETag"),
                    "last_modified": chapter_response.headers.get("Last-Modified"),
                    "updated_at": now_iso(),
                }
                manifest_entries.append(
                    {
                        **asdict(entry),
                        "key": key,
                        "file_path": known["file_path"],
                        "content_hash": markdown_hash,
                    }
                )
                continue

            fetched_at = datetime.now(UTC).isoformat()
            file_path = write_markdown_chapter(entry, markdown_text, markdown_hash, fetched_at)

            known_entries[key] = {
                "file_path": file_path,
                "content_hash": markdown_hash,
                "etag": chapter_response.headers.get("ETag"),
                "last_modified": chapter_response.headers.get("Last-Modified"),
                "source_url": entry.url,
                "updated_at": fetched_at,
            }

            if known:
                summary.updated += 1
            else:
                summary.new += 1

            manifest_entries.append(format_entry_for_manifest(entry, file_path, markdown_hash))
        except Exception:
            summary.errors += 1

    state["entries"] = known_entries
    state["last_toc_hash"] = current_toc_hash
    state["last_sync_at"] = now_iso()

    save_state(state)

    # Rebuild manifest from ALL known state entries in TOC order (cumulative across arcs)
    all_manifest: list[dict[str, Any]] = []
    for toc_entry in all_entries:
        k = toc_entry.identity_key
        st = known_entries.get(k)
        if st and st.get("file_path"):
            all_manifest.append(
                {
                    **asdict(toc_entry),
                    "key": k,
                    "file_path": st["file_path"],
                    "content_hash": st.get("content_hash", ""),
                }
            )
    save_manifest(all_manifest)

    return {
        "summary": asdict(summary),
        "counts": counts,
        "entries": len(filtered_entries),
    }
