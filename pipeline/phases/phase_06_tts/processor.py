"""
Phase 06 — Voice Assignment Processor
"""

import time
from .input_schema import Phase06Input
from .output_schema import Phase06Output


_DEFAULT_VOICES = [
    "en-US-AriaNeural",
    "en-US-JennyNeural",
    "en-US-GuyNeural",
    "en-GB-LibbyNeural",
    "en-GB-RyanNeural",
]


def _build_voice_registry(character_registry: list[dict], settings: dict) -> list[dict]:
    provider = settings.get("tts_provider", "edge")
    configured = settings.get("character_voice_map", {})
    character_voice_pool = _DEFAULT_VOICES[1:] if len(_DEFAULT_VOICES) > 1 else _DEFAULT_VOICES

    registry = [
        {
            "voice_id": "voice_narrator",
            "character_id": None,
            "provider": provider,
            "voice_name": settings.get("narrator_voice", _DEFAULT_VOICES[0]),
        }
    ]

    for idx, character in enumerate(character_registry, start=1):
        character_id = character["character_id"]
        voice_name = configured.get(character_id) or character_voice_pool[
            (idx - 1) % len(character_voice_pool)
        ]
        registry.append(
            {
                "voice_id": f"voice_{character_id}",
                "character_id": character_id,
                "provider": provider,
                "voice_name": voice_name,
            }
        )

    return registry


def _voice_lookup(voice_registry: list[dict]) -> dict[str | None, dict]:
    return {entry.get("character_id"): entry for entry in voice_registry}


def _segment_character_id(enriched_segment: dict) -> str | None:
    if enriched_segment.get("segment_type") == "dialogue":
        return enriched_segment.get("speaker_id")
    if enriched_segment.get("segment_type") == "thought":
        return enriched_segment.get("thought_owner_id")
    return None


def _build_voice_segment(enriched_segment: dict, voice_map: dict[str | None, dict]) -> dict:
    character_id = _segment_character_id(enriched_segment)
    voice = voice_map.get(character_id) or voice_map[None]

    return {
        "segment_id": enriched_segment.get("segment_id"),
        "character_id": character_id,
        "voice_id": voice["voice_id"],
        "segment_type": enriched_segment.get("segment_type", "narration"),
        "text": enriched_segment.get("text", ""),
    }


def process(input_data: Phase06Input) -> Phase06Output:
    start = time.time()

    voice_registry = _build_voice_registry(input_data.character_registry, input_data.settings)
    voice_map = _voice_lookup(voice_registry)
    voice_segments = [
        _build_voice_segment(segment, voice_map) for segment in input_data.enriched_segments
    ]

    output = Phase06Output(
        voice_segments=voice_segments,
        voice_registry=voice_registry,
        meta={
            "phase": "06_voice_assignment",
            "version": "1.0.0",
            "timestamp": time.time(),
        },
        input_summary={
            "enriched_segment_count": len(input_data.enriched_segments),
            "character_count": len(input_data.character_registry),
        },
        output_summary={
            "voice_segment_count": len(voice_segments),
            "voice_registry_count": len(voice_registry),
        },
        errors=[],
        warnings=[],
        timings={"total_ms": (time.time() - start) * 1000},
    )

    return output
