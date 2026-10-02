"""
Phase 02 — Processor Tests
Copilot: Follow Phase 00 and Phase 01 patterns EXACTLY.
"""

from pipeline.phases.phase_02_normalize.processor import process
from pipeline.phases.phase_02_normalize.input_schema import Phase02Input

def test_process_basic():
    input_data = Phase02Input(
        chapter_index=[{"chapter_id": "ch1"}],
        raw_payloads={"ch1": "<p>Hello world</p>"},
        settings={"config_version": "1.0"}
    )

    output = process(input_data)

    assert "normalized_chapters" in output.dict()
    assert "chapter_stats" in output.dict()
