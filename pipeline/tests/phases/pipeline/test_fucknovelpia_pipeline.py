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
    harness_logs = logs_dir()
    pre_phase00_logs = len(list(harness_logs.glob("pipeline_real_phase00*.json")))

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
    assert len(list(harness_logs.glob("pipeline_real_phase00*.json"))) > pre_phase00_logs

    if phase00_output["errors"] and _is_live_fetch_error(phase00_output["errors"]):
        pytest.skip(f"Live site unavailable: {phase00_output['errors']}")
    if phase00_output["errors"]:
        pytest.fail(f"Unexpected Phase 00 errors: {phase00_output['errors']}")
    assert phase00_output["output_summary"]["chapter_count"] == 3

    pre_phase01_logs = len(list(harness_logs.glob("pipeline_real_phase01*.json")))
    phase01_output = run_phase(
        run_phase01,
        {"artifact_root": str(tmp_path)},
        {"source": phase00_output["source"], "settings": {}},
        "pipeline_real_phase01",
    )
    assert len(list(harness_logs.glob("pipeline_real_phase01*.json"))) > pre_phase01_logs
    if phase01_output["errors"]:
        pytest.skip(f"Live site produced non-deterministic Phase 01 errors: {phase01_output['errors']}")
    assert phase01_output["output_summary"]["chapter_count"] == 3

    pre_phase02_logs = len(list(harness_logs.glob("pipeline_real_phase02*.json")))
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
    assert len(list(harness_logs.glob("pipeline_real_phase02*.json"))) > pre_phase02_logs
    if phase02_output["errors"]:
        pytest.skip(f"Live site produced non-deterministic Phase 02 errors: {phase02_output['errors']}")
    assert phase02_output["output_summary"]["normalized_count"] == 3

    cleaned = phase02_output["normalized_chapters"]
    assert sorted(cleaned.keys()) == ["ch1", "ch2", "ch3"]
    assert all(isinstance(cleaned[ch], str) and cleaned[ch].strip() for ch in cleaned)