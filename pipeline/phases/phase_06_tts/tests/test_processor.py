"""
Phase 06 — Processor Tests
Copilot: Follow Phase 00–05 patterns EXACTLY.
"""

from pipeline.phases.phase_06_audio.processor import process
from pipeline.phases.phase_06_audio.input_schema import Phase06Input

def test_process_basic():
    input_data = Phase06Input(
        script_segments=[{
            "script_id": "scr1",
            "chapter_id": "ch1",
            "text": "Hello world",
            "voice": {"style": "default"},
            "pacing": {"pause_ms": 150}
        }],
        script_index={"scr1": {}},
        settings={"config_version": "1.0"}
    )

    output = process(input_data)

    assert "audio_chunks" in output.dict()
    assert "audio_index" in output.dict()
