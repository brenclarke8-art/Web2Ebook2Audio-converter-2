"""
Phase 03 — Processor Tests
Copilot: Follow Phase 00–02 patterns EXACTLY.
"""

from pipeline.phases.phase_03_segment.processor import process
from pipeline.phases.phase_03_segment.input_schema import Phase03Input

def test_process_basic():
    input_data = Phase03Input(
        normalized_chapters={"ch1": "Hello world. This is a test."},
        chapter_stats={"ch1": {}},
        settings={"config_version": "1.0"}
    )

    output = process(input_data)

    assert "segments" in output.dict()
    assert "segment_index" in output.dict()
