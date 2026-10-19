from pipeline.phases.phase_03_segmentation.processor import process
from pipeline.phases.phase_03_segmentation.input_schema import Phase03Input


def test_process_basic():
    input_data = Phase03Input(
        normalized_chapters={"ch1": "Hello world. This is a test."},
        chapter_stats={"ch1": {}},
        settings={"config_version": "1.0"},
    )

    output = process(input_data)

    assert "segments" in output.dict()
    assert "segmentation_stats" in output.dict()
    assert output.segments[0]["segment_id"].startswith("ch1_seg")
