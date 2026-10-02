"""
Phase 09 — Runner Tests
Copilot: Follow Phase 00–08 patterns EXACTLY.
"""

from pathlib import Path
from pipeline.phases.phase_09_export.runner import run

def test_runner_executes(tmp_path):
    context = {"artifact_root": str(tmp_path)}

    input_artifact = {
        "package_manifest": {
            "audiobook": {
                "chapters": [{
                    "chapter_id": "ch1",
                    "stitched_id": "sti1",
                    "path": "placeholder/a.wav",
                    "metadata": {"duration_ms": 1000, "sample_rate": 22050, "format": "wav"}
                }]
            },
            "epub": {"chapters": [], "metadata": {}}
        },
        "package_index": {},
        "settings": {"title": "Test Book"}
    }

    output = run(context, input_artifact)
    assert "meta" in output
