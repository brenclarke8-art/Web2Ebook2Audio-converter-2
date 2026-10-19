from pipeline.phases.phase_05_voice_assignment.processor import process
from pipeline.phases.phase_05_voice_assignment.input_schema import Phase05Input


def test_process_basic():
    input_data = Phase05Input(
        segments=[
            {
                "segment_id": "seg1",
                "chapter_id": "ch1",
                "text": '"Hello," Sarah said.',
                "text_markers": ["double_quote"],
            }
        ],
        character_registry=[
            {
                "character_id": "char_001",
                "canonical_name": "Sarah Carter",
                "aliases": ["Sarah", "Sarah Carter"],
                "importance": "major",
                "first_seen_segment": "seg1",
                "character_profile": {},
            }
        ],
        settings={"config_version": "1.0"},
    )

    output = process(input_data)

    assert "enriched_segments" in output.dict()
    assert "enrichment_stats" in output.dict()
    assert output.enriched_segments[0].primary_type == "dialogue"
    assert output.enriched_segments[0].speaker_id == "char_001"
