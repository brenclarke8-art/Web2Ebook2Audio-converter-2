from pipeline.phases.phase_00_fetch.chapter_parser import (
    extract_chapter_urls,
    extract_content,
    extract_title,
    load_rules_for_domain,
)
from pipeline.tests.harness.utils import tests_root


def _read_phase00_fixture(name: str) -> str:
    path = tests_root() / "fixtures" / "phase_00" / name
    return path.read_text(encoding="utf-8")


def test_rule_based_extraction_with_synthetic_fixtures():
    index_url = "https://fucknovelpia.com/novel/synthetic-episode-novel"
    rules = load_rules_for_domain(index_url)

    assert rules["chapter_list_selector"] == "div.episode-list a.episode-item"
    assert rules["title_selector"] == "h1.episode-title"
    assert rules["content_selector"] == "div.episode-content"

    index_html = _read_phase00_fixture("index_fucknovelpia.html")
    urls = extract_chapter_urls(index_html, rules, index_url)

    assert urls == [
        "https://fucknovelpia.com/novel/synthetic-episode-novel/episode-1",
        "https://fucknovelpia.com/novel/synthetic-episode-novel/episode-2",
        "https://fucknovelpia.com/novel/synthetic-episode-novel/episode-3",
    ]

    chapter_html = _read_phase00_fixture("chapter_fucknovelpia_1.html")
    assert extract_title(chapter_html, rules) == "Episode 1: Arrival"

    content_html = extract_content(chapter_html, rules)
    assert content_html.startswith('<div class="episode-content">')