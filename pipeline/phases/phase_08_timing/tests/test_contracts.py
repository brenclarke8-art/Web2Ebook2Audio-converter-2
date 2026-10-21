"""
Phase 07 — Contract Tests
Copilot: Follow Phase 00–06 patterns EXACTLY.
"""

from pipeline.phases.phase_07_stitch.output_schema import Phase07Output

def test_contract_fields_exist():
    output = Phase07Output(
        stitched_audio=[],
        stitched_index={},
        meta={},
        input_summary={},
        output_summary={},
        errors=[],
        warnings=[],
        timings={}
    )

    assert hasattr(output, "stitched_audio")
    assert hasattr(output, "stitched_index")
    assert hasattr(output, "meta")
