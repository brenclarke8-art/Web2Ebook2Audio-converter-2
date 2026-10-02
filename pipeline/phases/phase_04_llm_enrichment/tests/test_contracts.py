"""
Phase 04 — Contract Tests
Copilot: Follow Phase 00–03 patterns EXACTLY.
"""

from pipeline.phases.phase_04_enrich.output_schema import Phase04Output

def test_contract_fields_exist():
    output = Phase04Output(
        enriched_segments=[],
        enriched_index={},
        meta={},
        input_summary={},
        output_summary={},
        errors=[],
        warnings=[],
        timings={}
    )

    assert hasattr(output, "enriched_segments")
    assert hasattr(output, "enriched_index")
    assert hasattr(output, "meta")
