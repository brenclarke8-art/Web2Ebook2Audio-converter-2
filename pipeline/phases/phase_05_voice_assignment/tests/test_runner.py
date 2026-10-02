"""
Phase 05 — Runner Tests
Copilot: Follow Phase 00–04 patterns EXACTLY.
"""

from pipeline.phases.phase_05_script.runner import run

def test_runner_executes():
    context = {"artifact_root": "pipeline/artifacts"}
    input_artifact = {
        "enriched_segments": [{"segment_id": "seg1", "chapter_id": "ch1", "text": "Hello"}],
        "enriched_index": {"seg1": {}},
        "settings": {"config_version": "1.0"}
    }

    output = run(context, input_artifact)
    assert "meta" in output
