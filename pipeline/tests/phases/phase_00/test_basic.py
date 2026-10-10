from pipeline.phases.phase_00_fetch.runner import run
from pipeline.tests.harness.runner import run_phase
from pipeline.tests.phases.phase_00.helpers import read_phase00_fixture


def test_basic_extraction_with_synthetic_fixtures(monkeypatch, tmp_path):
    index_url = "https://fucknovelpia.com/novel/synthetic-episode-novel"
    chapter_urls = {
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
            return {
                "ok": True,
                "status": 200,
                "html": read_phase00_fixture("index_fucknovelpia.html"),
                "error": None,
            }
        if url in chapter_urls:
            return {"ok": True, "status": 200, "html": chapter_urls[url], "error": None}
        return {"ok": False, "status": 404, "html": "", "error": "not mocked"}

    monkeypatch.setattr("pipeline.phases.phase_00_fetch.processor.fetch_html", fake_fetch)

    input_artifact = {
        "index_url": index_url,
        "chapter_range": [1, 3],
        "settings": {},
        "env": {},
    }
    context = {"artifact_dir": str(tmp_path)}

    output = run_phase(run, context, input_artifact, "phase00_basic_synthetic")

    assert output["output_summary"]["chapter_count"] == 3
    assert len(output["source"]["chapters"]) == 3
    assert output["errors"] == []