"""
Phase 08 — Processor Tests
Copilot: Follow Phase 00–07 patterns EXACTLY.
"""

from pipeline.phases.phase_08_package.processor import process
from pipeline.phases.phase_08_package.input_schema import Phase08Input

def test_process_basic():
    input_data = Phase08Input(
        stitched_audio=[{
            "stitched_id": "sti1",
            "chapter_id": "ch1",
            "path": "placeholder/a.wav",
            "metadata": {"duration_ms": 1000, "sample_rate": 22050, "format": "wav"}
        }],
        stitched_index={"sti1": {}},
        settings={"title": "Test Book", "author": "Tester"}
    )

    output = process(input_data)

    assert "package_manifest" in output.dict()
    assert "package_index" in output.dict()
