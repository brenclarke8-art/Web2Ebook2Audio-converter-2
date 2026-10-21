"""
Phase 08 — Contract Tests
Copilot: Follow Phase 00–07 patterns EXACTLY.
"""

from pipeline.phases.phase_08_package.output_schema import Phase08Output

def test_contract_fields_exist():
    output = Phase08Output(
        package_manifest={},
        package_index={},
        meta={},
        input_summary={},
        output_summary={},
        errors=[],
        warnings=[],
        timings={}
    )

    assert hasattr(output, "package_manifest")
    assert hasattr(output, "package_index")
    assert hasattr(output, "meta")
