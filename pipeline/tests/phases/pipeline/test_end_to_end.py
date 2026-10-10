from pipeline.phases.phase_00_fetch.runner import run as run_phase00
from pipeline.phases.phase_01_source.runner import run as run_phase01
from pipeline.phases.phase_02_cleaning.runner import run as run_phase02
from pipeline.tests.harness.runner import run_phase
from pipeline.tests.phases.phase_00.helpers import read_phase00_fixture


def test_pipeline_end_to_end_with_synthetic_fixtures(monkeypatch, tmp_path):
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

    phase00_output = run_phase(
        run_phase00,
        {"artifact_dir": str(tmp_path)},
        {"index_url": index_url, "chapter_range": [1, 3], "settings": {}, "env": {}},
        "pipeline_synth_phase00",
    )
    phase01_output = run_phase(
        run_phase01,
        {"artifact_root": str(tmp_path)},
        {"source": phase00_output["source"], "settings": {}},
        "pipeline_synth_phase01",
    )
    phase02_output = run_phase(
        run_phase02,
        {"artifact_root": str(tmp_path)},
        {
            "chapter_index": phase01_output["chapter_index"],
            "raw_payloads": phase01_output["raw_payloads"],
            "settings": {},
        },
        "pipeline_synth_phase02",
    )

    assert phase00_output["output_summary"]["chapter_count"] == 3
    assert phase01_output["output_summary"]["chapter_count"] == 3
    assert phase02_output["output_summary"]["normalized_count"] == 3

    assert phase00_output["errors"] == []
    assert phase01_output["errors"] == []
    assert phase02_output["errors"] == []

    assert phase00_output["output_summary"]["final_range"] == [1, 3]
    assert phase01_output["input_summary"]["source_type"] == "web"
    assert phase02_output["input_summary"]["chapter_count"] == 3