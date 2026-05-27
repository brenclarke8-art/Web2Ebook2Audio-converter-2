from ebook_app.models.multispeaker_tts import (
    build_normalized_voice_lookup,
    resolve_voice_for_segment,
)


def test_voice_resolution_prefers_explicit_mapping_over_gender_defaults():
    mappings = {"narrator": "af_heart", "Alice": "bf_emma"}
    lookup = build_normalized_voice_lookup(mappings)

    resolved = resolve_voice_for_segment(
        speaker="Alice",
        gender="female",
        voice_mappings=mappings,
        narrator_voice="af_heart",
        default_male_voice="am_adam",
        default_female_voice="af_sarah",
        normalized_lookup=lookup,
    )

    assert resolved.voice == "bf_emma"
    assert resolved.resolution in {"exact", "normalized"}


def test_voice_resolution_falls_back_to_gender_then_narrator():
    mappings = {"narrator": "af_heart"}
    lookup = build_normalized_voice_lookup(mappings)

    male_resolved = resolve_voice_for_segment(
        speaker="Unknown Person",
        gender="male",
        voice_mappings=mappings,
        narrator_voice="af_heart",
        default_male_voice="am_adam",
        default_female_voice="af_sarah",
        normalized_lookup=lookup,
    )
    assert male_resolved.voice == "am_adam"
    assert male_resolved.resolution == "fallback_gender"

    unknown_resolved = resolve_voice_for_segment(
        speaker="No Match",
        gender="unknown",
        voice_mappings=mappings,
        narrator_voice="af_heart",
        default_male_voice="am_adam",
        default_female_voice="af_sarah",
        normalized_lookup=lookup,
    )
    assert unknown_resolved.voice == "af_heart"
    assert unknown_resolved.resolution == "fallback"
