from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, Tuple, Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class VoiceResolution:
    requested_speaker: str
    matched_speaker: str
    voice: str
    resolution: str  # 'exact', 'normalized', 'alias', 'character_db', 'fallback_gender', 'fallback', 'narration'


def _normalize_speaker_like_parser(name: str) -> str:
    """
    Light normalization aligned with dialogue_parser:
    - strip whitespace
    - remove simple parenthetical suffixes: "John (angry)" -> "John"
    - strip trailing punctuation: "John..." -> "John"
    - normalize internal whitespace
    """
    if not name:
        return "narrator"
    s = name.strip()

    # Remove simple parenthetical suffixes: "John (angry)" -> "John"
    if "(" in s and s.endswith(")"):
        s = s[: s.rfind("(")].rstrip()

    # Strip trailing punctuation like "John..." -> "John"
    while s and s[-1] in ".!?,":  # keep quotes out of here; they usually don't appear in mappings
        s = s[:-1].rstrip()

    # Normalize internal whitespace
    s = " ".join(s.split())
    return s or "narrator"


def _normalize_name(name: str) -> str:
    """
    Normalization for lookup keys:
    - apply parser-like normalization
    - lowercase for matching
    """
    base = _normalize_speaker_like_parser(name)
    return base.lower()


_HONORIFICS = {"mr", "mrs", "ms", "dr", "prof", "sir", "captain", "capt", "miss", "lord", "lady"}
_SUFFIXES = {"jr", "sr", "iii", "ii"}


def _alias_base(norm: str) -> str:
    """
    Aggressive alias base:
    - remove honorifics and suffixes
    - keep core name tokens
    """
    tokens = [t for t in norm.split(" ") if t]
    core: list[str] = []
    for t in tokens:
        t_clean = t.strip(".")
        if t_clean in _HONORIFICS or t_clean in _SUFFIXES:
            continue
        core.append(t_clean)
    return " ".join(core)


def build_normalized_voice_lookup(voice_mappings: Dict[str, str]) -> Dict[str, Tuple[str, str]]:
    """
    Build a lookup from normalized speaker name → (original_speaker_name, voice_name).
    Normalization is parser-aligned + lowercased for matching.
    """
    lookup: Dict[str, Tuple[str, str]] = {}
    for speaker, voice in voice_mappings.items():
        norm = _normalize_name(speaker)
        lookup[norm] = (speaker, voice)
    return lookup


def _match_alias(norm: str, normalized_lookup: Dict[str, Tuple[str, str]]) -> Tuple[str, str] | None:
    """
    Aggressive alias matching:
    - compare alias bases
    - allow partial matches between requested and known keys
    """
    if not normalized_lookup:
        return None

    requested_base = _alias_base(norm)
    if not requested_base:
        return None

    # Exact base match first
    for key, (speaker, voice) in normalized_lookup.items():
        if _alias_base(key) == requested_base:
            return speaker, voice

    # Partial containment match
    for key, (speaker, voice) in normalized_lookup.items():
        key_base = _alias_base(key)
        if not key_base:
            continue
        if requested_base in key_base or key_base in requested_base:
            return speaker, voice

    return None


def resolve_voice_mapping(
    speaker: str,
    voice_mappings: Dict[str, str],
    *,
    narrator_voice: str,
    normalized_lookup: Dict[str, Tuple[str, str]],
) -> VoiceResolution:
    """
    Resolve a speaker name to a voice, with normalization, alias matching, and narrator fallback.
    """
    requested = speaker or "narrator"

    # 1) Exact key match
    if requested in voice_mappings:
        voice = voice_mappings[requested]
        return VoiceResolution(
            requested_speaker=requested,
            matched_speaker=requested,
            voice=voice,
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

    # 3) Alias match
    alias_match = _match_alias(norm, normalized_lookup)
    if alias_match is not None:
        matched_speaker, voice = alias_match
        return VoiceResolution(
            requested_speaker=requested,
            matched_speaker=matched_speaker,
            voice=voice,
            resolution="alias",
        )

    # 4) Fallback to narrator
    return VoiceResolution(
        requested_speaker=requested,
        matched_speaker="narrator",
        voice=narrator_voice,
        resolution="fallback",
    )


def _resolve_character_db_voice(speaker: str, character_db: Any | None) -> str | None:
    """
    Try to resolve a voice from a character DB using duck-typing.
    Expected possibilities:
    - character_db.get_voice(name)
    - character_db.voices[name]
    - character_db.get(name) -> object with .voice or ['voice']
    """
    if not character_db or not speaker:
        return None

    try:
        if hasattr(character_db, "get_voice"):
            v = character_db.get_voice(speaker)
            if isinstance(v, str) and v:
                return v

        voices = getattr(character_db, "voices", None)
        if isinstance(voices, dict) and speaker in voices:
            v = voices.get(speaker)
            if isinstance(v, str) and v:
                return v

        if hasattr(character_db, "get"):
            obj = character_db.get(speaker)
            if obj is not None:
                if isinstance(obj, dict) and "voice" in obj and isinstance(obj["voice"], str):
                    return obj["voice"]
                v_attr = getattr(obj, "voice", None)
                if isinstance(v_attr, str) and v_attr:
                    return v_attr
    except Exception:  # noqa: BLE001
        # We keep this silent to avoid breaking TTS on DB issues.
        return None

    return None


def resolve_voice_for_segment(
    *,
    speaker: str,
    gender: str,
    segment_type: Literal["dialogue", "thought", "narration"] = "dialogue",
    voice_mappings: Dict[str, str],
    narrator_voice: str,
    default_male_voice: str,
    default_female_voice: str,
    normalized_lookup: Dict[str, Tuple[str, str]],
    character_db: Any | None = None,
    debug: bool = False,
) -> VoiceResolution:
    """
    Resolve voice using:
    1) Segment type (narration → narrator)
    2) Speaker mapping (exact / normalized / alias)
    3) Character DB voice
    4) Gender defaults
    5) Narrator fallback
    """
    # 0) Segment-type handling: narration always uses narrator voice
    if segment_type == "narration":
        if debug:
            logger.debug(
                "Segment type 'narration' → narrator voice (%s) for speaker '%s'",
                narrator_voice,
                speaker,
            )
        return VoiceResolution(
            requested_speaker=speaker or "narrator",
            matched_speaker="narrator",
            voice=narrator_voice,
            resolution="narration",
        )

    # Normalize speaker like parser for display, but keep original for requested
    normalized_speaker_display = _normalize_speaker_like_parser(speaker)
    requested = normalized_speaker_display or "narrator"

    # 1) Early narrator fallback for narrator/unknown/empty
    if requested in {"narrator", "unknown", ""}:
        if debug:
            logger.debug(
                "Speaker '%s' treated as narrator → narrator voice (%s)",
                requested,
                narrator_voice,
            )
        return VoiceResolution(
            requested_speaker=requested,
            matched_speaker="narrator",
            voice=narrator_voice,
            resolution="fallback",
        )

    # 2) Speaker mapping (exact / normalized / alias / narrator fallback)
    base = resolve_voice_mapping(
        requested,
        voice_mappings,
        narrator_voice=narrator_voice,
        normalized_lookup=normalized_lookup,
    )

    if debug:
        logger.debug(
            "Base voice resolution for '%s': matched='%s', voice='%s', resolution='%s'",
            requested,
            base.matched_speaker,
            base.voice,
            base.resolution,
        )

    # If we already resolved to narrator, respect that and stop
    if base.matched_speaker == "narrator":
        if debug:
            logger.debug(
                "Base resolution already narrator for '%s' → using narrator voice (%s)",
                requested,
                base.voice,
            )
        return base

    # If we have an explicit mapping (exact/normalized/alias), use it
    if base.resolution in {"exact", "normalized", "alias"}:
        return base

    # 3) Character DB voice (if available)
    db_voice = _resolve_character_db_voice(requested, character_db)
    if db_voice:
        if debug:
            logger.debug(
                "Character DB voice for '%s' → %s",
                requested,
                db_voice,
            )
        return VoiceResolution(
            requested_speaker=requested,
            matched_speaker=requested,
            voice=db_voice,
            resolution="character_db",
        )

    # 4) Gender-based defaults
    gender_lc = (gender or "").strip().lower()
    if gender_lc == "male" and default_male_voice:
        if debug:
            logger.debug(
                "Gender fallback (male) for '%s' → %s",
                requested,
                default_male_voice,
            )
        return VoiceResolution(
            requested_speaker=requested,
            matched_speaker="__default_male__",
            voice=default_male_voice,
            resolution="fallback_gender",
        )
    if gender_lc == "female" and default_female_voice:
        if debug:
            logger.debug(
                "Gender fallback (female) for '%s' → %s",
                requested,
                default_female_voice,
            )
        return VoiceResolution(
            requested_speaker=requested,
            matched_speaker="__default_female__",
            voice=default_female_voice,
            resolution="fallback_gender",
        )

    # 5) Final narrator fallback
    if debug:
        logger.debug(
            "Final narrator fallback for '%s' → %s",
            requested,
            narrator_voice,
        )
    return VoiceResolution(
        requested_speaker=requested,
        matched_speaker="narrator",
        voice=narrator_voice,
        resolution="fallback",
    )
