"""
Phase 02 — Runner Tests
Copilot: Follow Phase 00 and Phase 01 patterns EXACTLY.
"""

from pipeline.phases.phase_02_normalize.runner import run

def test_runner_executes():
    context = {"artifact_root": "pipeline/artifacts"}
    input_artifact = {
        "chapter_index": [{"chapter_id": "ch1"}],
        "raw_payloads": {"ch1": "<p>Hello</p>"},
        "settings": {"config_version": "1.0"}
    }

    output = run(context, input_artifact)
    assert "meta" in output
