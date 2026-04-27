from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import markdown
import nh3
import yaml
from bs4 import BeautifulSoup

from rezeror.parser.storage import load_json

ALLOWED_HTML_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "del",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "img",
    "ol",
    "p",
    "pre",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}

ALLOWED_HTML_ATTRIBUTES: dict[str, set[str]] = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "loading"},
    "th": {"colspan", "rowspan"},
    "td": {"colspan", "rowspan"},
}

ALLOWED_HTML_PROTOCOLS = {"http", "https", "mailto"}


def format_chapter_display_title(metadata: dict[str, Any], fallback: str) -> str:
    raw_arc = str(metadata.get("arc") or "").strip()
    raw_chapter = str(metadata.get("chapter") or metadata.get("title") or "").strip()

    arc_part = ""
    chapter_part = ""

    arc_match = re.search(r"\barc\s+(\d+)\b", raw_arc, flags=re.IGNORECASE)
    if arc_match:
        arc_part = f"Arc {arc_match.group(1)}"

    chapter_match = re.search(r"\bchapter\s+(\d+)\b", raw_chapter, flags=re.IGNORECASE)
    if chapter_match:
        chapter_number = chapter_match.group(1)
        chapter_tail = raw_chapter[chapter_match.end() :].strip(" :-\u2013\u2014")
        chapter_part = f"Chapter {chapter_number}"
        if chapter_tail:
            chapter_part += f" {chapter_tail}"

    if arc_part and chapter_part:
        return f"{arc_part}, {chapter_part}"
    if chapter_part:
        return chapter_part
    if raw_chapter:
        return raw_chapter
    return fallback


def load_manifest_entries(manifest_path: Path) -> list[dict[str, Any]]:
    manifest = load_json(manifest_path, {"entries": []})
    return manifest.get("entries", [])


def safe_chapter_abs_path(chapter_path: str, chapters_dir: Path) -> Path:
    candidate = (chapters_dir / chapter_path).resolve()
    chapters_root = chapters_dir.resolve()
    if chapters_root not in candidate.parents and candidate != chapters_root:
        raise ValueError("Invalid chapter path")
    return candidate


def read_markdown_with_front_matter(chapter_path: str, chapters_dir: Path) -> tuple[dict[str, Any], str]:
    abs_path = safe_chapter_abs_path(chapter_path, chapters_dir)
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


def render_markdown_with_toc(markdown_text: str) -> tuple[str, list[dict[str, str]]]:
    md = markdown.Markdown(extensions=["toc", "fenced_code", "tables"])
    raw_html = md.convert(markdown_text)
    html = nh3.clean(
        raw_html,
        tags=ALLOWED_HTML_TAGS,
        attributes=ALLOWED_HTML_ATTRIBUTES,
        url_schemes=ALLOWED_HTML_PROTOCOLS,
    )

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


def adjacent_entries(chapter_path: str, entries: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    index = next((i for i, item in enumerate(entries) if item.get("file_path") == chapter_path), None)
    if index is None:
        return None, None

    prev_entry = entries[index - 1] if index > 0 else None
    next_entry = entries[index + 1] if index < len(entries) - 1 else None
    return prev_entry, next_entry


def group_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
