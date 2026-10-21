from pipeline.phases.phase_04_character_registry.output_schema import Phase04Output


def test_contract_fields_exist():
    output = Phase04Output(
        character_registry=[],
        segments=[],
        meta={},
        input_summary={},
        output_summary={},
        errors=[],
        warnings=[],
        timings={},
    )

    assert hasattr(output, "character_registry")
    assert hasattr(output, "segments")
    assert hasattr(output, "meta")
