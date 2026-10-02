"""
Phase 09 — Contract Tests
Copilot: Follow Phase 00–08 patterns EXACTLY.
"""

from pipeline.phases.phase_09_export.output_schema import Phase09Output

def test_contract_fields_exist():
    output = Phase09Output(
        export_manifest={},
        export_index={},
        meta={},
        input_summary={},
        output_summary={},
        errors=[],
        warnings=[],
        timings={}
    )

    assert hasattr(output, "export_manifest")
    assert hasattr(output, "export_index")
    assert hasattr(output, "meta")
