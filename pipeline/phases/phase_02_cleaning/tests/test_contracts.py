"""
Phase 02 — Contract Tests
Copilot: Follow Phase 00 and Phase 01 patterns EXACTLY.
"""

from pipeline.phases.phase_02_normalize.output_schema import Phase02Output

def test_contract_fields_exist():
    output = Phase02Output(
        normalized_chapters={},
        chapter_stats={},
        meta={},
        input_summary={},
        output_summary={},
        errors=[],
        warnings=[],
        timings={}
    )

    assert hasattr(output, "normalized_chapters")
    assert hasattr(output, "chapter_stats")
    assert hasattr(output, "meta")
