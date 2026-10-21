from pipeline.phases.phase_04_character_registry.processor import process
from pipeline.phases.phase_04_character_registry.input_schema import Phase04Input


def test_process_basic():
    input_data = Phase04Input(
        segments=[
            {"segment_id": "seg1", "chapter_id": "ch1", "text": "Sarah Carter spoke."},
            {"segment_id": "seg2", "chapter_id": "ch1", "text": "Sarah Carter replied."},
        ],
        settings={"config_version": "1.0"},
    )

    output = process(input_data)

    assert "character_registry" in output.dict()
    assert "segments" in output.dict()
    assert output.character_registry[0].character_id.startswith("char_")
    assert output.character_registry[0].first_seen_segment == "seg1"
    assert output.character_registry[0].character_profile == {}
