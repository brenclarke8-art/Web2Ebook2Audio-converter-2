"""
Phase 01 — Processor Tests

Copilot Instructions:
- Follow Phase 00 test_processor.py EXACTLY.
- Do NOT add behavioral tests here.
- Only verify that process() returns a Phase01Output with required fields.
- Do NOT import or reference legacy code.
- Do NOT test chapter extraction logic; that belongs to processor implementation.
"""

from pipeline.phases.phase_01_source.processor import process
from pipeline.phases.phase_01_source.input_schema import Phase01Input

def test_process_basic():
    input_data = Phase01Input(
        source={"type": "web", "url": "https://example.com"},
        settings={"config_version": "1.0"}
    )

    output = process(input_data)

    assert "meta" in output.dict()
    assert "chapter_index" in output.dict()
    assert "raw_payloads" in output.dict()
    assert "input_summary" in output.dict()
    assert "output_summary" in output.dict()
    assert "errors" in output.dict()
    assert "warnings" in output.dict()
    assert "timings" in output.dict()
