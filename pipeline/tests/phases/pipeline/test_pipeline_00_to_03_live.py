# tests/pipeline/test_pipeline_00_to_06.py

from pipeline.phases.phase_00_fetch.runner import run as run_phase00
from pipeline.phases.phase_01_source.runner import run as run_phase01
from pipeline.phases.phase_02_cleaning.runner import run as run_phase02
from pipeline.phases.phase_03_segmentation.runner import run as run_phase03

from pipeline.tests.harness.runner import run_phase
from pipeline.tests.harness.utils import logs_dir
from pipeline.tests.phases.helpers import (
    REAL_FUCKNOVELPIA_INDEX_URL,
    is_live_fetch_error_message,
)

import pytest


@pytest.mark.live
def test_pipeline_00_to_03(tmp_path):
    """
    Integration test focused on execution continuity.

    Goal:
        Fetch
        -> Source
        -> Cleaning
        -> Segmentation

    Not validating quality yet.
    Only validating successful execution and artifact generation.
    """

    harness_logs = logs_dir()

    #
    # PHASE 00
    #
    phase00_output = run_phase(
        run_phase00,
        {"artifact_dir": str(tmp_path)},
        {
            "index_url": REAL_FUCKNOVELPIA_INDEX_URL,
            "chapter_range": [1, 3],
            "settings": {},
            "env": {},
        },
        "pipeline_00",
    )

    if phase00_output["errors"]:
        if all(
            is_live_fetch_error_message(error)
            for error in phase00_output["errors"]
        ):
            pytest.skip(
                f"Live site unavailable: {phase00_output['errors']}"
            )

        pytest.fail(
            f"Unexpected Phase 00 errors: {phase00_output['errors']}"
        )

    #
    # PHASE 01
    #
    phase01_output = run_phase(
        run_phase01,
        {"artifact_root": str(tmp_path)},
        {
            "source": phase00_output["source"],
            "settings": {},
        },
        "pipeline_01",
    )

    assert phase01_output["errors"] == []

    #
    # PHASE 02
    #
    phase02_output = run_phase(
        run_phase02,
        {"artifact_root": str(tmp_path)},
        {
            "chapter_index": phase01_output["chapter_index"],
            "raw_payloads": phase01_output["raw_payloads"],
            "settings": {},
        },
        "pipeline_02",
    )

    assert phase02_output["errors"] == []

    #
    # PHASE 03
    #
    phase03_output = run_phase(
        run_phase03,
        {"artifact_root": str(tmp_path)},
        {
            "normalized_chapters": phase02_output["normalized_chapters"],
            "chapter_stats": phase02_output["chapter_stats"],
            "settings": {},
        },
        "pipeline_03",
    )

    assert phase03_output["errors"] == []

    #
    # BASIC CONTINUITY CHECKS
    #
    assert phase00_output["output_summary"]["chapter_count"] > 0

    assert len(phase01_output["chapter_index"]) > 0
    assert len(phase01_output["raw_payloads"]) > 0

    assert len(phase02_output["normalized_chapters"]) > 0

    assert len(phase03_output["segments"]) > 0

    print(
        {
            "phase00_chapters":
                phase00_output["output_summary"]["chapter_count"],

            "phase01_chapters":
                phase01_output["output_summary"]["chapter_count"],

            "phase02_normalized":
                phase02_output["output_summary"]["normalized_count"],

            "phase03_segments":
                len(phase03_output["segments"]),
        }
    )