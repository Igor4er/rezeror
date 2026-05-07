from __future__ import annotations

from hashlib import sha256

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as html_to_markdown_lib


NON_CONTENT_SELECTORS = (
    "script",
    "style",
    "noscript",
    "form",
    "#comments",
    ".comments",
    ".comments-area",
    ".comment-list",
    ".comment-respond",
    "#respond",
    ".sharedaddy",
    "#jp-post-flair",
    ".post-meta-container",
    ".entry-author",
    ".navigation.post-navigation",
    "nav.post-navigation",
)


def _strip_non_chapter_sections(container: Tag) -> None:
    for selector in NON_CONTENT_SELECTORS:
        for bad in container.select(selector):
            bad.decompose()


def extract_chapter_content_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    container = (
        soup.select_one("article .entry-content")
        or soup.select_one("article .post-content")
        or soup.select_one(".entry-content")
        or soup.select_one(".post-content")
        or soup.select_one("main")
        or soup.body
    )
    if container is None:
        raise ValueError("Could not locate chapter content container")

    _strip_non_chapter_sections(container)

    return str(container)


def html_fragment_to_markdown(html_fragment: str) -> str:
    markdown = html_to_markdown_lib(
        html_fragment,
        heading_style="ATX",
        bullets="-",
        strip=["script", "style", "noscript"],
    )
    return markdown.strip() + "\n"


def content_hash(markdown_text: str) -> str:
    return sha256(markdown_text.encode("utf-8")).hexdigest()
