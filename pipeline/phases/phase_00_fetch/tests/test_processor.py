from pipeline.phases.phase_00_fetch.processor import process
from pipeline.phases.phase_00_fetch.input_schema import Phase00FetchInput

def test_processor_runs_minimal(monkeypatch):
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

    inp = Phase00FetchInput(
        index_url="https://example.com",
        chapter_range=[1, 1],
        settings={},
        env={}
    )

    out = process(inp)

    assert hasattr(out, "source")
    assert hasattr(out, "warnings")
    assert out.source["chapter_range"] == [1, 1]
    assert out.output_summary["chapter_count"] == 1
    assert out.source["chapters"][0]["title"] == "Test Chapter"
