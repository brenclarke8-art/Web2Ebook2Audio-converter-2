from pipeline.phases.phase_00_fetch.runner import run
from pipeline.tests.harness.runner import run_phase
from pipeline.tests.phases.phase_00.helpers import read_phase00_fixture


def test_missing_index_url(tmp_path):
    output = run_phase(
        run,
        {"artifact_dir": str(tmp_path)},
        {"index_url": "", "chapter_range": [1, 3], "settings": {}, "env": {}},
        "phase00_failure_missing_index",
    )

    assert any("Index URL is empty." in error for error in output["errors"])
    assert output["source"] == {}


def test_failed_fetch(monkeypatch, tmp_path):
    def failed_fetch(_url):
        return {"ok": False, "status": 500, "html": "", "error": "network down"}

    monkeypatch.setattr("pipeline.phases.phase_00_fetch.processor.fetch_html", failed_fetch)

    output = run_phase(
        run,
        {"artifact_dir": str(tmp_path)},
        {
            "index_url": "https://fucknovelpia.com/novel/synthetic-episode-novel",
            "chapter_range": [1, 3],
            "settings": {},
            "env": {},
        },
        "phase00_failure_fetch",
    )

    assert any("Failed to fetch index URL" in error for error in output["errors"])
    assert output["source"] == {}


def test_empty_chapter_list(monkeypatch, tmp_path):
    def fake_fetch(_url):
        return {"ok": True, "status": 200, "html": "<html><body><p>No links</p></body></html>", "error": None}

    monkeypatch.setattr("pipeline.phases.phase_00_fetch.processor.fetch_html", fake_fetch)

    output = run_phase(
        run,
        {"artifact_dir": str(tmp_path)},
        {
            "index_url": "https://fucknovelpia.com/novel/synthetic-episode-novel",
            "chapter_range": [1, 3],
            "settings": {},
            "env": {},
        },
        "phase00_failure_empty_chapters",
    )

    assert any("No chapter URLs found." in error for error in output["errors"])
    assert output["source"] == {}


def test_invalid_chapter_range_is_clamped(monkeypatch, tmp_path):
    index_url = "https://fucknovelpia.com/novel/synthetic-episode-novel"
    index_html = read_phase00_fixture("index_fucknovelpia.html")
    chapter_html = {
        "https://fucknovelpia.com/novel/synthetic-episode-novel/episode-1": read_phase00_fixture(
            "chapter_fucknovelpia_1.html"
        ),
        "https://fucknovelpia.com/novel/synthetic-episode-novel/episode-2": read_phase00_fixture(
            "chapter_fucknovelpia_2.html"
        ),
        "https://fucknovelpia.com/novel/synthetic-episode-novel/episode-3": read_phase00_fixture(
            "chapter_fucknovelpia_3.html"
        ),
    }

    def fake_fetch(url):
        if url == index_url:
            return {"ok": True, "status": 200, "html": index_html, "error": None}
        if url in chapter_html:
            return {"ok": True, "status": 200, "html": chapter_html[url], "error": None}
        return {"ok": False, "status": 404, "html": "", "error": "not mocked"}

    monkeypatch.setattr("pipeline.phases.phase_00_fetch.processor.fetch_html", fake_fetch)

    output = run_phase(
        run,
        {"artifact_dir": str(tmp_path)},
        {
            "index_url": index_url,
            # Processor behavior:
            # requested_start=99 -> start_idx=min(99, total=3)=3
            # requested_end=2 -> end_idx=min(2, total=3)=2 -> max(start_idx=3, 2)=3
            "chapter_range": [99, 2],
            "settings": {},
            "env": {},
        },
        "phase00_failure_invalid_range",
    )

    assert output["errors"] == []
    assert output["source"]["chapter_range"] == [3, 3]
    assert output["output_summary"]["chapter_count"] == 1