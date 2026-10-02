"""
Phase 03 — Contract Tests
Copilot: Follow Phase 00–02 patterns EXACTLY.
"""

from pipeline.phases.phase_03_segment.output_schema import Phase03Output

def test_contract_fields_exist():
    output = Phase03Output(
        segments=[],
        segment_index={},
        meta={},
        input_summary={},
        output_summary={},
        errors=[],
        warnings=[],
        timings={}
    )

    assert hasattr(output, "segments")
    assert hasattr(output, "segment_index")
    assert hasattr(output, "meta")
