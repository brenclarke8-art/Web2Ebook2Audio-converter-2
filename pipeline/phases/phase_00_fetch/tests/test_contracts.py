from pipeline.phases.phase_00_fetch.output_schema import Phase00FetchOutput

def test_output_contract():
    out = Phase00FetchOutput(
        source={},
        meta={},
        input_summary={},
        output_summary={},
        errors=[],
        warnings=[],
        timings={}
    )

    # Field existence
    assert hasattr(out, "source")
    assert hasattr(out, "meta")
    assert hasattr(out, "input_summary")
    assert hasattr(out, "output_summary")
    assert hasattr(out, "errors")
    assert hasattr(out, "warnings")
    assert hasattr(out, "timings")

    # Basic type checks
    assert isinstance(out.errors, list)
    assert isinstance(out.warnings, list)
    assert isinstance(out.model_dump(), dict)
