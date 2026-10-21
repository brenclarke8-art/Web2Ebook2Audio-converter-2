from pipeline.phases.phase_06_voice_assignment.output_schema import Phase06Output


def test_contract_fields_exist():
    output = Phase06Output(
        voice_segments=[],
        voice_registry=[],
        meta={},
        input_summary={},
        output_summary={},
        errors=[],
        warnings=[],
        timings={},
    )

    assert hasattr(output, "voice_segments")
    assert hasattr(output, "voice_registry")
    assert hasattr(output, "meta")
