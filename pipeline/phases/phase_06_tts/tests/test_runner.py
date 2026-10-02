"""
Phase 06 — Runner Tests
Copilot: Follow Phase 00–05 patterns EXACTLY.
"""

from pipeline.phases.phase_06_audio.runner import run

def test_runner_executes():
    context = {"artifact_root": "pipeline/artifacts"}
    input_artifact = {
        "script_segments": [{
            "script_id": "scr1",
            "chapter_id": "ch1",
            "text": "Hello",
            "voice": {"style": "default"},
            "pacing": {"pause_ms": 150}
        }],
        "script_index": {"scr1": {}},
        "settings": {"config_version": "1.0"}
    }

    output = run(context, input_artifact)
    assert "meta" in output
