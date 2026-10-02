"""
Phase 01 — Runner Tests

Copilot Instructions:
- Follow Phase 00 test_runner.py EXACTLY.
- Do NOT add behavioral tests here.
- Only verify that run() executes and returns a dict with required fields.
- Do NOT import or reference legacy code.
- Do NOT test processor logic; that belongs to test_processor.py.
"""

from pipeline.phases.phase_01_source.runner import run

def test_runner_executes():
    context = {"artifact_root": "pipeline/artifacts"}
    input_artifact = {
        "source": {"type": "web", "url": "https://example.com"},
        "settings": {"config_version": "1.0"}
    }

    output = run(context, input_artifact)
    assert "meta" in output
    assert isinstance(output, dict)
