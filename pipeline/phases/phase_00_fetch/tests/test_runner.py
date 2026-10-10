import os
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
        if "example.com" in url:
            return {"ok": True, "status": 200, "html": fake_index_html, "error": None}
        return {"ok": True, "status": 200, "html": fake_chapter_html, "error": None}

    monkeypatch.setattr(
        "pipeline.phases.phase_00_fetch.fetcher.fetch_html",
        fake_fetch
    )

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
