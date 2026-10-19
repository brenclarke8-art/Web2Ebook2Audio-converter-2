from pipeline.phases.phase_06_tts.processor import process
from pipeline.phases.phase_06_tts.input_schema import Phase06Input


def test_process_basic():
    input_data = Phase06Input(
        enriched_segments=[
            {
                "segment_id": "seg1",
                "text": "Hello world",
                "segment_type": "dialogue",
                "speaker_id": "char_001",
                "thought_owner_id": None,
                "referenced_characters": ["char_001"],
                "confidence": 0.95,
            }
        ],
        character_registry=[
            {
                "character_id": "char_001",
                "canonical_name": "Sarah Carter",
                "aliases": ["Sarah"],
                "gender": "female",
                "importance": "major",
            }
        ],
        settings={"config_version": "1.0"},
    )

    output = process(input_data)

    assert "voice_segments" in output.dict()
    assert "voice_registry" in output.dict()
    assert output.voice_segments[0]["voice_id"].startswith("voice_")
