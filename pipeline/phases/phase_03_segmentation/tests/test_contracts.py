from pipeline.phases.phase_03_segmentation.output_schema import Phase03Output


def test_contract_fields_exist():
    output = Phase03Output(
        segments=[],
        segmentation_stats={},
        meta={},
        input_summary={},
        output_summary={},
        errors=[],
        warnings=[],
        timings={},
    )

    assert hasattr(output, "segments")
    assert hasattr(output, "segmentation_stats")
    assert hasattr(output, "meta")
