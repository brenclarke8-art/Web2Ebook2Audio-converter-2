from pipeline.phases.phase_03_segmentation.processor import process
from pipeline.phases.phase_03_segmentation.input_schema import Phase03Input


def test_process_basic():
    input_data = Phase03Input(
        normalized_chapters={
            "ch1": "CHAPTER ONE\n\n\"Hello world,\" Sarah said.\n\n***\n\n_Quiet thoughts_."
        },
        chapter_stats={"ch1": {}},
        settings={"config_version": "1.0"},
    )

    output = process(input_data)

    assert "segments" in output.dict()
    assert "segmentation_stats" in output.dict()
    assert output.segments[0].segment_id == "ch1_seg0001"
    assert output.segments[0].structural_type == "chapter_title"
    assert output.segments[1].text_markers == ["double_quote"]
    assert output.segments[2].structural_type == "scene_break"
    assert "italicized" in output.segments[3].text_markers
    assert output.segments[1].sequence == 2
