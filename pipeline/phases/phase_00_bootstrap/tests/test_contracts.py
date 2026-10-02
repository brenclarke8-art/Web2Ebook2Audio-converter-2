from pipeline.phases.phase_00_bootstrap.output_schema import Phase00Output

def test_contract_fields_exist():
    output = Phase00Output(
        normalized_config={},
        readiness_report={},
        meta={},
        input_summary={},
        output_summary={},
        errors=[],
        warnings=[],
        timings={}
    )

    assert hasattr(output, "meta")
    assert hasattr(output, "timings")
    assert hasattr(output, "errors")
    assert hasattr(output, "warnings")
