from pipeline.phases.phase_01_source.runner import run
from pipeline.tests.harness.runner import run_phase
from pipeline.tests.phases.phase_01.helpers import load_phase01_source_fixture


def test_structure_keys_metadata_and_ordering(tmp_path):
    output = run_phase(
        run,
        {"artifact_root": str(tmp_path)},
        {"source": load_phase01_source_fixture(), "settings": {}},
        "phase01_structure_synthetic",
    )

    assert set(output.keys()) == {
        "chapter_index",
        "raw_payloads",
        "meta",
        "input_summary",
        "output_summary",
        "errors",
        "warnings",
        "timings",
    }

    assert output["meta"]["phase"] == "01_source"
    assert output["meta"]["version"] == "1.0.0"
    assert isinstance(output["meta"]["timestamp"], (int, float))

    assert output["input_summary"]["source_type"] == "web"
    assert output["output_summary"]["chapter_count"] == 3

    assert [item["order"] for item in output["chapter_index"]] == [1, 2, 3]
    assert [item["chapter_id"] for item in output["chapter_index"]] == ["ch1", "ch2", "ch3"]