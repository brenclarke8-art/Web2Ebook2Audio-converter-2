"""
Phase 05 — Processor Tests
Copilot: Follow Phase 00–04 patterns EXACTLY.
"""

from pipeline.phases.phase_05_script.processor import process
from pipeline.phases.phase_05_script.input_schema import Phase05Input

def test_process_basic():
    input_data = Phase05Input(
        enriched_segments=[{"segment_id": "seg1", "chapter_id": "ch1", "text": "Hello world"}],
        enriched_index={"seg1": {}},
        settings={"config_version": "1.0"}
    )

    output = process(input_data)

    assert "script_segments" in output.dict()
    assert "script_index" in output.dict()
