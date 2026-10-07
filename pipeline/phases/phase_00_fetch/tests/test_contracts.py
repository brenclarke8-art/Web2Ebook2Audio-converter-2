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
    assert hasattr(out, "source")
    assert hasattr(out, "meta")
    assert hasattr(out, "warnings")
