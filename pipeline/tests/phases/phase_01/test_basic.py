from pipeline.phases.phase_01_source.runner import run
from pipeline.tests.harness.runner import run_phase
from pipeline.tests.phases.phase_01.helpers import load_phase01_source_fixture


def test_chapter_index_and_raw_payloads_from_synthetic_phase00_output(tmp_path):
    source = load_phase01_source_fixture()

    output = run_phase(
        run,
        {"artifact_root": str(tmp_path)},
        {"source": source, "settings": {}},
        "phase01_basic_synthetic",
    )

    assert len(output["chapter_index"]) == 3
    assert [item["chapter_id"] for item in output["chapter_index"]] == ["ch1", "ch2", "ch3"]
    assert [item["title"] for item in output["chapter_index"]] == [
        "Episode 1: Arrival",
        "Episode 2: Shift",
        "Episode 3: Decision",
    ]

    assert sorted(output["raw_payloads"].keys()) == ["ch1", "ch2", "ch3"]
    assert "Hana reached the gate." in output["raw_payloads"]["ch1"]
    assert "river road." in output["raw_payloads"]["ch2"]
    assert "sealed the pact." in output["raw_payloads"]["ch3"]