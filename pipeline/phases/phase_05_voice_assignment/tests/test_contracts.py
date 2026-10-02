"""
Phase 05 — Contract Tests
Copilot: Follow Phase 00–04 patterns EXACTLY.
"""

from pipeline.phases.phase_05_script.output_schema import Phase05Output

def test_contract_fields_exist():
    output = Phase05Output(
        script_segments=[],
        script_index={},
        meta={},
        input_summary={},
        output_summary={},
        errors=[],
        warnings=[],
        timings={}
    )

    assert hasattr(output, "script_segments")
    assert hasattr(output, "script_index")
    assert hasattr(output, "meta")
