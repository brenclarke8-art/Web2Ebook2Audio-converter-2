from pipeline.phases.phase_05_semantic_enrichment.output_schema import Phase05Output


def test_contract_fields_exist():
    output = Phase05Output(
        enriched_segments=[],
        character_registry=[],
        enrichment_stats={},
        meta={},
        input_summary={},
        output_summary={},
        errors=[],
        warnings=[],
        timings={},
    )

    assert hasattr(output, "enriched_segments")
    assert hasattr(output, "character_registry")
    assert hasattr(output, "enrichment_stats")
