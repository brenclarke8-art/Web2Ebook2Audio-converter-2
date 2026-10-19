from pipeline.phases.phase_03_segmentation.runner import run


def test_runner_executes(tmp_path):
    context = {"artifact_root": str(tmp_path)}
    input_artifact = {
        "normalized_chapters": {"ch1": "Chapter 1\n\nHello world."},
        "chapter_stats": {"ch1": {}},
        "settings": {"config_version": "1.0"},
    }

    output = run(context, input_artifact)
    assert "meta" in output
    assert "segmentation_stats" in output
    assert output["segments"][0]["structural_type"] == "chapter_title"
