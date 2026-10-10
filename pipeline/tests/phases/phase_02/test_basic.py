from pipeline.phases.phase_02_cleaning.runner import run
from pipeline.tests.harness.runner import run_phase
from pipeline.tests.phases.phase_02.helpers import (
    load_phase02_raw_payloads_fixture,
    synthetic_chapter_index,
)


def test_basic_cleaning_with_synthetic_raw_payloads(tmp_path):
    raw_payloads = load_phase02_raw_payloads_fixture()

    output = run_phase(
        run,
        {"artifact_root": str(tmp_path)},
        {
            "chapter_index": synthetic_chapter_index(),
            "raw_payloads": raw_payloads,
            "settings": {},
        },
        "phase02_basic_synthetic",
    )

    normalized = output["normalized_chapters"]
    assert sorted(normalized.keys()) == ["ch1", "ch2", "ch3"]

    # HTML stripping
    assert "<div" not in normalized["ch1"]
    assert "<p>" not in normalized["ch1"]

    # Paragraph segmentation
    assert "\n\n" in normalized["ch1"]

    # Whitespace normalization
    assert "  " not in normalized["ch1"]
    assert "\t" not in normalized["ch1"]