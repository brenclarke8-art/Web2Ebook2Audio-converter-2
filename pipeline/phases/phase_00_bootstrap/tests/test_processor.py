from pipeline.phases.phase_00_bootstrap.processor import process
from pipeline.phases.phase_00_bootstrap.input_schema import Phase00Input

def test_process_basic():
    input_data = Phase00Input(
        settings={"version": "1.2"},
        env={"MODE": "test"}
    )

    output = process(input_data)

    assert output.normalized_config["config_version"] == "1.2"
    assert output.normalized_config["env_mode"] == "test"
    assert output.readiness_report["settings_loaded"] is True
