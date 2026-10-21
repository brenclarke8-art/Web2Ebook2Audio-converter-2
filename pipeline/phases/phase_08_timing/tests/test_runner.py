"""
Phase 07 — Runner Tests
Copilot: Follow Phase 00–06 patterns EXACTLY.
"""

from pipeline.phases.phase_07_stitch.runner import run

def test_runner_executes():
    context = {"artifact_root": "pipeline/artifacts"}
    input_artifact = {
        "audio_chunks": [{
            "audio_id": "aud1",
            "script_id": "scr1",
            "chapter_id": "ch1",
            "path": "placeholder/a.wav",
            "metadata": {"duration_ms": 1000, "sample_rate": 22050, "format": "wav"}
        }],
        "audio_index": {"aud1": {}},
        "settings": {"config_version": "1.0"}
    }

    output = run(context, input_artifact)
    assert "meta" in output
