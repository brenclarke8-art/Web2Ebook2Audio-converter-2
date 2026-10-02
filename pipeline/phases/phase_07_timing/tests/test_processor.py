"""
Phase 07 — Processor Tests
Copilot: Follow Phase 00–06 patterns EXACTLY.
"""

from pipeline.phases.phase_07_stitch.processor import process
from pipeline.phases.phase_07_stitch.input_schema import Phase07Input

def test_process_basic():
    input_data = Phase07Input(
        audio_chunks=[{
            "audio_id": "aud1",
            "script_id": "scr1",
            "chapter_id": "ch1",
            "path": "placeholder/a.wav",
            "metadata": {"duration_ms": 1000, "sample_rate": 22050, "format": "wav"}
        }],
        audio_index={"aud1": {}},
        settings={"config_version": "1.0"}
    )

    output = process(input_data)

    assert "stitched_audio" in output.dict()
    assert "stitched_index" in output.dict()
