from pipeline.phases.phase_06_voice_assignment.processor import process
from pipeline.phases.phase_06_voice_assignment.input_schema import Phase06Input


def test_process_manual_mode_basic():
    input_data = Phase06Input(
        enriched_segments=[
            {
                "segment_id": "seg1",
                "primary_type": "dialogue",
                "speaker_id": "char_001",
                "thought_owner_id": None,
                "pov_character_id": "char_001",
                "referenced_characters": ["char_001"],
                "emotion_tag": None,
                "classification_confidence": 0.95,
                "speaker_confidence": 0.9,
            }
        ],
        character_registry=[
            {
                "character_id": "char_001",
                "canonical_name": "Sarah Carter",
                "aliases": ["Sarah"],
                "importance": "major",
                "first_seen_segment": "seg1",
                "character_profile": {},
            }
        ],
        settings={
            "config_version": "1.0",
            "tts": {
                "voice_mode": "manual",
                "manual": {
                    "narrator_voice": "Aria",
                    "character_voice_map": {"char_001": "Jenny"},
                },
            },
        },
    )

    output = process(input_data)

    assert "voice_segments" in output.dict()
    assert "voice_registry" in output.dict()
    assert output.voice_segments[0].voice_id == "voice_char_001"
    character_voice = next(v for v in output.voice_registry if v.character_id == "char_001")
    assert character_voice.voice_name == "Jenny"


def test_process_adaptive_mode_uses_profile_hint():
    input_data = Phase06Input(
        enriched_segments=[
            {
                "segment_id": "seg1",
                "primary_type": "dialogue",
                "speaker_id": "char_001",
                "thought_owner_id": None,
                "pov_character_id": "char_001",
                "referenced_characters": ["char_001"],
                "emotion_tag": "happy",
                "classification_confidence": 0.95,
                "speaker_confidence": 0.9,
            }
        ],
        character_registry=[
            {
                "character_id": "char_001",
                "canonical_name": "Sarah Carter",
                "aliases": ["Sarah"],
                "importance": "major",
                "first_seen_segment": "seg1",
                "character_profile": {"tts_hints": {"preferred_voice": "CustomVoiceA"}},
            }
        ],
        settings={"config_version": "1.0", "tts": {"voice_mode": "adaptive"}},
    )

    output = process(input_data)

    character_voice = next(v for v in output.voice_registry if v.character_id == "char_001")
    assert character_voice.voice_name == "CustomVoiceA"


def test_process_adaptive_mode_falls_back_to_pool():
    input_data = Phase06Input(
        enriched_segments=[
            {
                "segment_id": "seg1",
                "primary_type": "dialogue",
                "speaker_id": "char_001",
                "thought_owner_id": None,
                "pov_character_id": "char_001",
                "referenced_characters": ["char_001"],
                "emotion_tag": None,
                "classification_confidence": 0.8,
                "speaker_confidence": 0.6,
            }
        ],
        character_registry=[
            {
                "character_id": "char_001",
                "canonical_name": "Sarah Carter",
                "aliases": ["Sarah"],
                "importance": "major",
                "first_seen_segment": "seg1",
                "character_profile": {},
            }
        ],
        settings={"config_version": "1.0", "tts": {"voice_mode": "adaptive"}},
    )

    output = process(input_data)

    character_voice = next(v for v in output.voice_registry if v.character_id == "char_001")
    assert character_voice.voice_name in {
        "en-US-GuyNeural",
        "en-GB-LibbyNeural",
        "en-GB-RyanNeural",
        "en-US-EmmaNeural",
    }
