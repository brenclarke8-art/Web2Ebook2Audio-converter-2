import os
import json
from pipeline.phases.phase_00_fetch.runner import run

def test_runner_executes(monkeypatch, tmp_path):
    # Fake index HTML with two chapter links
    fake_index_html = """
        <html>
            <body>
                <a href="/ch1">Chapter 1</a>
                <a href="/ch2">Chapter 2</a>
            </body>
        </html>
    """

    # Fake chapter HTML
    fake_chapter_html = "<h1>Test Chapter</h1><div>Content</div>"

    # Mock fetch_html to avoid network calls
    def fake_fetch(url):
        if url == "https://example.com":
            return {"ok": True, "status": 200, "html": fake_index_html, "error": None}
        return {"ok": True, "status": 200, "html": fake_chapter_html, "error": None}

    monkeypatch.setattr("pipeline.phases.phase_00_fetch.processor.fetch_html", fake_fetch)

    context = {"artifact_dir": str(tmp_path)}
    input_artifact = {
        "index_url": "https://example.com",
        "chapter_range": [1, 1],
        "settings": {},
        "env": {}
    }

    out = run(context, input_artifact)

    # Runner returns a dict
    assert isinstance(out, dict)

    # Debug artifacts should exist
    debug_dir = tmp_path / "phase_00_fetch"
    assert (debug_dir / "source.json").exists()
    assert (debug_dir / "warnings.json").exists()
    assert (debug_dir / "meta.json").exists()

    # Output structure checks
    assert "source" in out
    assert "warnings" in out
    assert out["source"]["chapter_range"] == [1, 1]
    assert out["output_summary"]["chapter_count"] == 1


def test_runner_learns_rule_and_writes_debug_artifacts(monkeypatch, tmp_path):
    index_url = "https://example.com/novel/book/"
    fake_index_html = """
        <html><body>
            <a href="/novel/book/chapter-3/">Chapter 3</a>
            <a href="/novel/book/chapter-1/">Chapter 1</a>
            <a href="/novel/book/chapter-2/">Chapter 2</a>
        </body></html>
    """
    fake_chapter_html = "<h1>Learned Chapter</h1><div>Content</div>"

    def fake_fetch(url):
        if url == index_url:
            return {"ok": True, "status": 200, "html": fake_index_html, "error": None}
        return {"ok": True, "status": 200, "html": fake_chapter_html, "error": None}

    rules_path = tmp_path / "scraper_rules.json"
    rules_path.write_text(json.dumps({}), encoding="utf-8")

    monkeypatch.setattr("pipeline.phases.phase_00_fetch.processor.fetch_html", fake_fetch)
    monkeypatch.setattr("pipeline.phases.phase_00_fetch.infer_rules.RULES_PATH", rules_path)
    monkeypatch.setattr("pipeline.phases.phase_00_fetch.chapter_parser.RULES_PATH", rules_path)

    context = {"artifact_dir": str(tmp_path)}
    input_artifact = {
        "index_url": index_url,
        "chapter_range": [1, 2],
        "chapter_example_1": "https://example.com/novel/book/chapter-1/",
        "chapter_example_2": "https://example.com/novel/book/chapter-2/",
        "chapter_example_3": "https://example.com/novel/book/chapter-3/",
        "settings": {},
        "env": {},
    }

    out = run(context, input_artifact)

    assert out["errors"] == []
    assert out["output_summary"]["rule_learned"] is True
    assert out["source"]["chapters"][0]["source"].endswith("/chapter-1/")
    assert out["source"]["chapters"][1]["source"].endswith("/chapter-2/")

    rule_data = json.loads(rules_path.read_text(encoding="utf-8"))
    assert rule_data["example.com"]["learned"] is True
    assert rule_data["example.com"]["chapter_pattern"] == "https://example.com/novel/book/chapter-{n}/"

    debug_dir = tmp_path / "phase_00_fetch" / "debug"
    assert (debug_dir / "inferred_pattern.json").exists()
    assert (debug_dir / "generated_rule.json").exists()
    assert (debug_dir / "learned_examples.json").exists()
    assert (debug_dir / "final_chapter_template.json").exists()
