from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from rezeror.parser.models import TocEntry


def canonicalize_url(url: str, base_url: str) -> str:
    absolute = urljoin(base_url, url)
    split = urlsplit(absolute)
    scheme = split.scheme.lower()
    netloc = split.netloc.lower()
    query = urlencode(sorted(parse_qsl(split.query, keep_blank_values=True)))
    normalized = urlunsplit((scheme, netloc, split.path, query, ""))
    return normalized


def _iter_stream_tags(container: Tag) -> Iterable[Tag]:
    for node in container.descendants:
        if isinstance(node, Tag):
            yield node


def parse_toc_entries(html: str, toc_url: str) -> list[TocEntry]:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.select_one("article#post-35 .entry-content")
    if container is None:
        raise ValueError("TOC container article#post-35 .entry-content not found")

    entries: list[TocEntry] = []
    current_arc: str | None = None
    current_phase: str | None = None
    inside_arc_content = False
    order = 0

    for node in _iter_stream_tags(container):
        if node.name == "h1":
            heading = node.get_text(" ", strip=True)
            heading_lower = heading.lower()
            if heading_lower.startswith("arc "):
                current_arc = heading
                current_phase = None
                inside_arc_content = True
                continue
            if heading_lower.startswith("phase ") and current_arc:
                current_phase = heading
                continue
            if inside_arc_content and heading_lower.startswith("side content"):
                break

        if node.name == "ul" and current_arc:
            for li in node.find_all("li", recursive=False):
                anchor = li.find("a")
                if anchor is None:
                    continue
                href = anchor.get("href", "").strip()
                title = anchor.get_text(" ", strip=True)
                if not href or not title:
                    continue
                order += 1
                entries.append(
                    TocEntry(
                        title=title,
                        url=canonicalize_url(href, toc_url),
                        arc=current_arc,
                        phase=current_phase,
                        chapter=title,
                        order=order,
                    )
                )

    return entries


def toc_hash(entries: list[TocEntry]) -> str:
    data = [asdict(entry) for entry in entries]
    encoded = repr(data).encode("utf-8")
    return sha256(encoded).hexdigest()


def build_arc_phase_counts(entries: list[TocEntry]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for entry in entries:
        arc_bucket = counts.setdefault(entry.arc, {})
        phase_name = entry.phase or "(no phase)"
        arc_bucket[phase_name] = arc_bucket.get(phase_name, 0) + 1
    return counts
