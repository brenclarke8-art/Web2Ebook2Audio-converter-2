from pipeline.phases.phase_04_llm_enrichment.runner import run


def test_runner_executes(tmp_path):
    context = {"artifact_root": str(tmp_path)}
    input_artifact = {
        "segments": [{"segment_id": "seg1", "chapter_id": "ch1", "text": "Hello"}],
        "settings": {"config_version": "1.0"},
    }

    output = run(context, input_artifact)
    assert "meta" in output
    assert "character_registry" in output
