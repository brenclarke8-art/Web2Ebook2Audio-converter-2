from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class VoiceResolution:
    requested_speaker: str
    matched_speaker: str
    voice: str
    resolution: str  # 'exact', 'normalized', 'fallback'


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def build_normalized_voice_lookup(voice_mappings: Dict[str, str]) -> Dict[str, Tuple[str, str]]:
    """
    Build a lookup from normalized speaker name → (original_speaker_name, voice_name).
    """
    lookup: Dict[str, Tuple[str, str]] = {}
    for speaker, voice in voice_mappings.items():
        norm = _normalize_name(speaker)
        lookup[norm] = (speaker, voice)
    return lookup


def resolve_voice_mapping(
    speaker: str,
    voice_mappings: Dict[str, str],
    *,
    narrator_voice: str,
    normalized_lookup: Dict[str, Tuple[str, str]],
) -> VoiceResolution:
    """
    Resolve a speaker name to a voice, with normalization and fallback.
    """
    requested = speaker or "narrator"

    # 1) Exact key match
    if requested in voice_mappings:
        return VoiceResolution(
            requested_speaker=requested,
            matched_speaker=requested,
            voice=voice_mappings[requested],
            resolution="exact",
        )

    # 2) Normalized match
    norm = _normalize_name(requested)
    if norm in normalized_lookup:
        matched_speaker, voice = normalized_lookup[norm]
        return VoiceResolution(
            requested_speaker=requested,
            matched_speaker=matched_speaker,
            voice=voice,
            resolution="normalized",
        )

    # 3) Fallback to narrator
    return VoiceResolution(
        requested_speaker=requested,
        matched_speaker="narrator",
        voice=narrator_voice,
        resolution="fallback",
    )
