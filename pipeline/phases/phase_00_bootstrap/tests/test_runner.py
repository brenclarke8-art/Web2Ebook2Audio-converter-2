from pipeline.phases.phase_00_bootstrap.runner import run

def test_runner_executes():
    context = {"artifact_root": "pipeline/artifacts"}
    input_artifact = {
        "settings": {"version": "1.0"},
        "env": {"MODE": "dev"}
    }

    output = run(context, input_artifact)

    assert output["normalized_config"]["env_mode"] == "dev"
    assert "meta" in output
