"""
Phase 06 — Voice Assignment Processor
"""

import time
from .input_schema import Phase06Input
from .output_schema import Phase06Output


_DEFAULT_VOICES = {
    "narrator": "en-US-AriaNeural",
    "fallback": "en-US-JennyNeural",
    "character_pool": [
        "en-US-GuyNeural",
        "en-GB-LibbyNeural",
        "en-GB-RyanNeural",
        "en-US-EmmaNeural",
    ],
}

_DEFAULT_GENERATION_SETTINGS = {"style": "neutral", "pitch": 0, "speed": 1.0}
_FALLBACK_SENTINEL = "__fallback__"


def _resolve_tts_settings(settings: dict) -> dict:
    tts = settings.get("tts", {})
    if not isinstance(tts, dict):
        return {"voice_mode": "manual"}
    voice_mode = tts.get("voice_mode", "manual")
    if voice_mode not in {"manual", "adaptive"}:
        voice_mode = "manual"
    tts = dict(tts)
    tts["voice_mode"] = voice_mode
    return tts


def _manual_config(tts_settings: dict) -> dict:
    manual = tts_settings.get("manual")
    if isinstance(manual, dict):
        return manual
    return {}


def _adaptive_voice_name(character: dict, fallback_voice: str, pool_index: int) -> str:
    profile = character.get("character_profile", {})
    hints = profile.get("tts_hints", {}) if isinstance(profile, dict) else {}
    if isinstance(hints, dict) and hints.get("preferred_voice"):
        return hints["preferred_voice"]
    pool = _DEFAULT_VOICES["character_pool"]
    return pool[pool_index % len(pool)] if pool else fallback_voice


def _build_voice_registry(character_registry: list[dict], settings: dict) -> list[dict]:
    tts = _resolve_tts_settings(settings)
    manual = _manual_config(tts)
    provider = tts.get("provider", settings.get("tts_provider", "edge"))
    voice_mode = tts["voice_mode"]

    narrator_voice = (
        manual.get("narrator_voice")
        or tts.get("narrator_voice")
        or settings.get("narrator_voice")
        or _DEFAULT_VOICES["narrator"]
    )
    fallback_voice = manual.get("fallback_voice") or _DEFAULT_VOICES["fallback"]
    manual_map = manual.get("character_voice_map")
    if not isinstance(manual_map, dict):
        manual_map = settings.get("character_voice_map", {})
    if not isinstance(manual_map, dict):
        manual_map = {}

    registry = [
        {
            "voice_id": "voice_narrator",
            "character_id": None,
            "voice_role": "narrator",
            "provider": provider,
            "voice_name": narrator_voice,
            "generation_settings": dict(_DEFAULT_GENERATION_SETTINGS),
        },
        {
            "voice_id": "voice_fallback",
            "character_id": None,
            "voice_role": "fallback",
            "provider": provider,
            "voice_name": fallback_voice,
            "generation_settings": dict(_DEFAULT_GENERATION_SETTINGS),
        },
    ]

    for idx, character in enumerate(character_registry, start=1):
        character_id = character["character_id"]
        manual_voice = manual_map.get(character_id)
        if voice_mode == "manual":
            voice_name = manual_voice or fallback_voice
        else:
            voice_name = manual_voice or _adaptive_voice_name(character, fallback_voice, idx - 1)

        registry.append(
            {
                "voice_id": f"voice_{character_id}",
                "character_id": character_id,
                "voice_role": "character",
                "provider": provider,
                "voice_name": voice_name,
                "generation_settings": dict(_DEFAULT_GENERATION_SETTINGS),
            }
        )

    return registry


def _voice_lookup(voice_registry: list[dict]) -> dict[str | None, dict]:
    return {entry.get("character_id"): entry for entry in voice_registry}


def _segment_character_id(enriched_segment: dict) -> str | None:
    primary_type = enriched_segment.get("primary_type")
    if primary_type == "dialogue":
        return enriched_segment.get("speaker_id")
    if primary_type == "thought":
        return enriched_segment.get("thought_owner_id")
    return None


def _build_voice_segment(enriched_segment: dict, voice_map: dict[str | None, dict]) -> dict:
    character_id = _segment_character_id(enriched_segment)
    fallback = voice_map.get(_FALLBACK_SENTINEL) or voice_map.get(None)
    if character_id and character_id in voice_map:
        voice = voice_map[character_id]
    elif enriched_segment.get("primary_type") == "narration":
        voice = voice_map.get(None, fallback)
    else:
        voice = fallback

    return {
        "segment_id": enriched_segment.get("segment_id"),
        "voice_id": voice["voice_id"],
        "character_id": character_id,
        "voice_role": voice.get("voice_role", "fallback"),
        "primary_type": enriched_segment.get("primary_type", "narration"),
    }


def process(input_data: Phase06Input) -> Phase06Output:
    start = time.time()

    voice_registry = _build_voice_registry(input_data.character_registry, input_data.settings)
    if not voice_registry:
        raise ValueError("voice_registry must not be empty")

    voice_map = _voice_lookup(voice_registry)
    voice_map[_FALLBACK_SENTINEL] = next(
        (v for v in voice_registry if v.get("voice_role") == "fallback"),
        voice_registry[0],
    )

    voice_segments = [
        _build_voice_segment(segment, voice_map) for segment in input_data.enriched_segments
    ]

    voice_mode = _resolve_tts_settings(input_data.settings)["voice_mode"]

    output = Phase06Output(
        voice_segments=voice_segments,
        voice_registry=voice_registry,
        meta={
            "phase": "06_voice_assignment",
            "version": "2.0.0",
            "timestamp": time.time(),
            "voice_mode": voice_mode,
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
