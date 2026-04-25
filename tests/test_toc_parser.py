from pathlib import Path

from rezeror.parser.chapters import html_fragment_to_markdown
from rezeror.parser.toc import parse_toc_entries


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "toc_sample.html"


def test_toc_parser_state_machine_and_side_content_stop() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    entries = parse_toc_entries(html, "https://witchculttranslation.com/table-of-content/")

    assert len(entries) == 4
    assert entries[0].arc.startswith("Arc 2")
    assert entries[1].url.startswith("https://docs.google.com")

    arc3 = [entry for entry in entries if entry.arc.startswith("Arc 3")]
    assert len(arc3) == 2
    assert arc3[0].url == arc3[1].url
    assert arc3[0].identity_key != arc3[1].identity_key
    assert all(entry.phase == "Phase 1 - Reunion" for entry in arc3)


def test_markdown_conversion_preserves_emphasis() -> None:
    html = "<div><p><strong>Bold</strong> and <em>italic</em> text.</p></div>"
    md = html_fragment_to_markdown(html)
    assert "**Bold**" in md
    assert "*italic*" in md
