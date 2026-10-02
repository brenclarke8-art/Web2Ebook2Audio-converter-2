"""
Phase 09 — Processor Tests
Copilot: Follow Phase 00–08 patterns EXACTLY.
"""

from pathlib import Path
from pipeline.phases.phase_09_export.processor import process
from pipeline.phases.phase_09_export.input_schema import Phase09Input

def test_process_basic(tmp_path):
    context = {"artifact_root": str(tmp_path)}

    input_data = Phase09Input(
        package_manifest={
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
        package_index={},
        settings={"title": "Test Book"}
    )

    output = process(input_data, context)

    assert "export_manifest" in output.dict()
    assert "export_index" in output.dict()
