import pytest

from pipeline.phases.phase_00_fetch.runner import run as run_phase00
from pipeline.phases.phase_01_source.runner import run as run_phase01
from pipeline.phases.phase_02_cleaning.runner import run as run_phase02
from pipeline.tests.harness.runner import run_phase
from pipeline.tests.harness.utils import logs_dir


def _is_live_fetch_error(errors):
    return any(error.startswith("Failed to fetch index URL:") for error in errors)


@pytest.mark.live
def test_real_fucknovelpia_pipeline_end_to_end(tmp_path):
    phase00_output = run_phase(
        run_phase00,
        {"artifact_dir": str(tmp_path)},
        {
            "index_url": "https://fucknovelpia.com/novel/i-became-a-6-gacha-character",
            "chapter_range": [1, 3],
            "settings": {},
            "env": {},
        },
        "pipeline_real_phase00",
    )

    if phase00_output["errors"] and _is_live_fetch_error(phase00_output["errors"]):
        pytest.xfail(f"Live site unavailable: {phase00_output['errors']}")

    phase01_output = run_phase(
        run_phase01,
        {"artifact_root": str(tmp_path)},
        {"source": phase00_output["source"], "settings": {}},
        "pipeline_real_phase01",
    )
    phase02_output = run_phase(
        run_phase02,
        {"artifact_root": str(tmp_path)},
        {
            "chapter_index": phase01_output["chapter_index"],
            "raw_payloads": phase01_output["raw_payloads"],
            "settings": {},
        },
        "pipeline_real_phase02",
    )

    assert phase00_output["output_summary"]["chapter_count"] == 3
    assert phase01_output["output_summary"]["chapter_count"] == 3
    assert phase02_output["output_summary"]["normalized_count"] == 3

    assert phase00_output["errors"] == []
    assert phase01_output["errors"] == []
    assert phase02_output["errors"] == []

    cleaned = phase02_output["normalized_chapters"]
    assert sorted(cleaned.keys()) == ["ch1", "ch2", "ch3"]
    assert all(isinstance(cleaned[ch], str) and cleaned[ch].strip() for ch in cleaned)

    harness_logs = logs_dir()
    assert any(harness_logs.glob("pipeline_real_phase00*.json"))
    assert any(harness_logs.glob("pipeline_real_phase01*.json"))
    assert any(harness_logs.glob("pipeline_real_phase02*.json"))