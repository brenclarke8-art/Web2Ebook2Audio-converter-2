# ebook_app/tts/audio_utils.py
from __future__ import annotations

from dataclasses import dataclass


def _normalize_name(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def build_normalized_voice_lookup(voice_mappings: dict[str, str] | None) -> dict[str, str]:
    return {_normalize_name(name): voice for name, voice in (voice_mappings or {}).items()}


@dataclass(frozen=True)
class VoiceResolution:
    voice: str
    resolution: str


def resolve_voice_for_segment(
    *,
    speaker: str,
    gender: str,
    voice_mappings: dict[str, str] | None,
    narrator_voice: str,
    default_male_voice: str,
    default_female_voice: str,
    normalized_lookup: dict[str, str] | None = None,
) -> VoiceResolution:
    mappings = voice_mappings or {}
    if speaker in mappings:
        return VoiceResolution(voice=mappings[speaker], resolution="exact")

    lookup = normalized_lookup if normalized_lookup is not None else build_normalized_voice_lookup(mappings)
    normalized = _normalize_name(speaker)
    if normalized in lookup:
        return VoiceResolution(voice=lookup[normalized], resolution="normalized")

    if (gender or "").strip().lower() == "male":
        return VoiceResolution(voice=default_male_voice, resolution="fallback_gender")
    if (gender or "").strip().lower() == "female":
        return VoiceResolution(voice=default_female_voice, resolution="fallback_gender")

    return VoiceResolution(voice=narrator_voice, resolution="fallback")


__all__ = [
    "VoiceResolution",
    "build_normalized_voice_lookup",
    "resolve_voice_for_segment",
]
