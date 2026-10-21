"""
Phase 08 — Runner Tests
Copilot: Follow Phase 00–07 patterns EXACTLY.
"""

from pipeline.phases.phase_08_package.runner import run

def test_runner_executes():
    context = {"artifact_root": "pipeline/artifacts"}
    input_artifact = {
        "stitched_audio": [{
            "stitched_id": "sti1",
            "chapter_id": "ch1",
            "path": "placeholder/a.wav",
            "metadata": {"duration_ms": 1000, "sample_rate": 22050, "format": "wav"}
        }],
        "stitched_index": {"sti1": {}},
        "settings": {"title": "Test Book"}
    }

    output = run(context, input_artifact)
    assert "meta" in output
