from __future__ import annotations

from pathlib import Path
import re
import unicodedata

import markdown
from bs4 import BeautifulSoup


ROOT_DIR = Path(__file__).resolve().parents[1]
CHAPTERS_DIR = ROOT_DIR / "data" / "chapters"

SEPARATOR_SEARCH_LIMIT = 45
NARRATIVE_SCAN_WINDOW = 80

CREDIT_MARKERS = (
    "translated by",
    "edited by",
    "proofread",
    "all rights",
    "original author",
    "japanese web novel source",
    "source:",
    "disclaimer",
)


def _strip_front_matter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return text
    return parts[1].lstrip("\n")


def _normalize_text(value: str) -> str:
    return re.sub(r"[\s\u3000]+", " ", value or "").strip()


def _is_symbol_or_punct(ch: str) -> bool:
    category = unicodedata.category(ch)
    return category.startswith("P") or category.startswith("S")


def _is_separator_like(raw_text: str) -> bool:
    compact = re.sub(r"[\s\u3000]+", "", raw_text or "")
    if len(compact) < 6:
        return False

    chars = list(compact)
    symbol_count = sum(1 for ch in chars if _is_symbol_or_punct(ch))
    unique_count = len(set(chars))
    symbol_ratio = symbol_count / len(chars)

    return symbol_ratio >= 0.8 and unique_count <= 5


def _looks_like_credit_line(raw_text: str) -> bool:
    text = _normalize_text(raw_text).lower()
    if not text:
        return True
    return any(marker in text for marker in CREDIT_MARKERS)


def _looks_narrative_like(raw_text: str) -> bool:
    text = _normalize_text(raw_text)
    if not text or _is_separator_like(text) or _looks_like_credit_line(text):
        return False

    letters = [ch for ch in text if unicodedata.category(ch).startswith("L")]
    lowercase = [ch for ch in text if unicodedata.category(ch) == "Ll"]
    has_sentence_punctuation = re.search(r"[.!?…]$|[.!?…][\"'”’)]+$", text) is not None

    if len(letters) < 8 or len(lowercase) < 3:
        return False

    if len(text) >= 40:
        return True

    return len(text) >= 18 and has_sentence_punctuation


def _chapter_blocks(md_text: str) -> list[str]:
    html = markdown.Markdown(extensions=["toc", "fenced_code", "tables"]).convert(md_text)
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select("p, li, blockquote, h2, h3, h4, h5, h6")
    return [_normalize_text(el.get_text(" ", strip=True)) for el in blocks]


def _find_auto_start_index(blocks: list[str]) -> int | None:
    if not blocks:
        return None

    first_separator = -1
    last_separator = -1
    separator_count = 0

    for i, text in enumerate(blocks[:SEPARATOR_SEARCH_LIMIT]):
        if _is_separator_like(text):
            if first_separator == -1:
                first_separator = i
            last_separator = i
            separator_count += 1

    if first_separator == -1 or first_separator > 20 or separator_count < 2:
        return None

    scan_start = last_separator + 1
    scan_end = min(len(blocks), scan_start + NARRATIVE_SCAN_WINDOW)
    for i in range(scan_start, scan_end):
        if _looks_narrative_like(blocks[i]):
            return i

    return None


def _iter_chapter_files() -> list[Path]:
    return sorted(CHAPTERS_DIR.rglob("*.md"))


def test_credit_skip_detector_finds_start_for_separator_pattern_chapters() -> None:
    chapter_files = _iter_chapter_files()
    assert chapter_files, "No chapter markdown files found under data/chapters"

    candidate_count = 0
    misses: list[Path] = []

    for chapter_file in chapter_files:
        text = chapter_file.read_text(encoding="utf-8")
        body = _strip_front_matter(text)
        blocks = _chapter_blocks(body)

        separators_in_window = sum(
            1 for block in blocks[:SEPARATOR_SEARCH_LIMIT] if _is_separator_like(block)
        )
        if separators_in_window < 2:
            continue

        candidate_count += 1
        if _find_auto_start_index(blocks) is None:
            misses.append(chapter_file)

    assert candidate_count > 0, "No separator-pattern chapters found to validate"
    assert not misses, (
        "Credit-skip detector failed on separator-pattern chapters: "
        + ", ".join(str(path.relative_to(ROOT_DIR)) for path in misses[:10])
    )
