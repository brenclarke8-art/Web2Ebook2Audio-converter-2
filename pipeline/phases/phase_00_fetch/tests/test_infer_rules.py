import pytest
import json

from pipeline.phases.phase_00_fetch.infer_rules import (
    RuleInferenceError,
    build_chapter_regex,
    build_chapter_template,
    generate_learned_rule,
    infer_chapter_pattern,
    save_learned_rule,
)


def test_infer_pattern_detection_chapter_dash_number():
    inference = infer_chapter_pattern(
        "https://example.com/novel/chapter-1",
        "https://example.com/novel/chapter-2",
        "https://example.com/novel/chapter-3",
    )

    assert inference["padding"] == 0
    assert inference["first_known_chapter"] == 1
    assert build_chapter_template(inference) == "https://example.com/novel/chapter-{n}"
    assert build_chapter_regex(inference) == r"^/novel/chapter\-([0-9]+)$"


def test_infer_zero_padding():
    inference = infer_chapter_pattern(
        "https://example.com/novel/chapter-001/",
        "https://example.com/novel/chapter-002/",
        "https://example.com/novel/chapter-003/",
    )

    assert inference["padding"] == 3
    assert build_chapter_template(inference) == "https://example.com/novel/chapter-{n:03}/"
    assert build_chapter_regex(inference) == r"^/novel/chapter\-([0-9]{3})/?$"


def test_infer_numeric_path_segments():
    inference = infer_chapter_pattern(
        "https://example.com/book/123/1",
        "https://example.com/book/123/2",
        "https://example.com/book/123/3",
    )

    assert inference["padding"] == 0
    assert inference["static_prefix"].endswith("/book/123/")
    assert build_chapter_template(inference) == "https://example.com/book/123/{n}"


def test_infer_episode_pattern():
    inference = infer_chapter_pattern(
        "https://example.com/story/episode-10",
        "https://example.com/story/episode-11",
        "https://example.com/story/episode-12",
    )

    assert inference["first_known_chapter"] == 10
    assert build_chapter_template(inference) == "https://example.com/story/episode-{n}"


def test_consecutive_validation_passes_for_100_101_102():
    inference = infer_chapter_pattern(
        "https://example.com/chapter-100",
        "https://example.com/chapter-101",
        "https://example.com/chapter-102",
    )
    assert inference["first_known_chapter"] == 100


def test_consecutive_validation_fails_for_non_consecutive_examples():
    with pytest.raises(RuleInferenceError, match="consecutive"):
        infer_chapter_pattern(
            "https://example.com/chapter-100",
            "https://example.com/chapter-105",
            "https://example.com/chapter-110",
        )


def test_domain_validation_fails():
    with pytest.raises(RuleInferenceError, match="same domain"):
        infer_chapter_pattern(
            "https://example.com/chapter-1",
            "https://other.com/chapter-2",
            "https://example.com/chapter-3",
        )


def test_generate_learned_rule_shape():
    domain, rule, debug = generate_learned_rule(
        index_url="https://example.com/novel/",
        chapter_example_1="https://example.com/novel/chapter-1/",
        chapter_example_2="https://example.com/novel/chapter-2/",
        chapter_example_3="https://example.com/novel/chapter-3/",
    )

    assert domain == "example.com"
    assert rule["learned"] is True
    assert rule["chapter_pattern"] == "https://example.com/novel/chapter-{n}/"
    assert rule["rule_version"] == 1
    assert "generated_rule" in debug


def test_save_learned_rule_updates_existing_domain_without_duplicates(monkeypatch, tmp_path):
    rules_path = tmp_path / "scraper_rules.json"
    rules_path.write_text(
        json.dumps(
            {
                "example.com": {
                    "title_selector": "h1.chapter-title",
                    "content_selector": "div.chapter-content",
                },
                "other.com": {"learned": True},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("pipeline.phases.phase_00_fetch.infer_rules.RULES_PATH", rules_path)

    updated = save_learned_rule(
        "example.com",
        {
            "learned": True,
            "chapter_pattern": "https://example.com/chapter-{n}",
            "chapter_regex": r"^/chapter-([0-9]+)$",
            "padding": 0,
            "first_known_chapter": 1,
            "rule_version": 1,
        },
    )

    data = json.loads(rules_path.read_text(encoding="utf-8"))
    assert set(data.keys()) == {"example.com", "other.com"}
    assert data["example.com"]["learned"] is True
    assert data["example.com"]["title_selector"] == "h1.chapter-title"
    assert updated["chapter_pattern"] == "https://example.com/chapter-{n}"
