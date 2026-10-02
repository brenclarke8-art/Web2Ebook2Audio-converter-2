"""
Phase 04 — Processor Tests
Copilot: Follow Phase 00–03 patterns EXACTLY.
"""

from pipeline.phases.phase_04_enrich.processor import process
from pipeline.phases.phase_04_enrich.input_schema import Phase04Input

def test_process_basic():
    input_data = Phase04Input(
        segments=[{"segment_id": "seg1", "chapter_id": "ch1", "text": "Hello world"}],
        segment_index={"seg1": {}},
        settings={"config_version": "1.0"}
    )

    output = process(input_data)

    assert "enriched_segments" in output.dict()
    assert "enriched_index" in output.dict()
