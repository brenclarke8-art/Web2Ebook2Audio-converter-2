"""
Phase 03 — Runner Tests
Copilot: Follow Phase 00–02 patterns EXACTLY.
"""

from pipeline.phases.phase_03_segment.runner import run

def test_runner_executes():
    context = {"artifact_root": "pipeline/artifacts"}
    input_artifact = {
        "normalized_chapters": {"ch1": "Hello world."},
        "chapter_stats": {"ch1": {}},
        "settings": {"config_version": "1.0"}
    }

    output = run(context, input_artifact)
    assert "meta" in output
