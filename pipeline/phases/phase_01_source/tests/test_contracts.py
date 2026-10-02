"""
Phase 01 — Contract Tests

Copilot Instructions:
- Follow Phase 00 test_contracts.py EXACTLY.
- Do NOT add behavioral tests here.
- Only verify that Phase01Output exposes the required fields.
- Do NOT import or reference legacy code.
"""

from pipeline.phases.phase_01_source.output_schema import Phase01Output

def test_contract_fields_exist():
    output = Phase01Output(
        chapter_index=[],
        raw_payloads={},
        meta={},
        input_summary={},
        output_summary={},
        errors=[],
        warnings=[],
        timings={}
    )

    assert hasattr(output, "chapter_index")
    assert hasattr(output, "raw_payloads")
    assert hasattr(output, "meta")
    assert hasattr(output, "input_summary")
    assert hasattr(output, "output_summary")
    assert hasattr(output, "errors")
    assert hasattr(output, "warnings")
    assert hasattr(output, "timings")
