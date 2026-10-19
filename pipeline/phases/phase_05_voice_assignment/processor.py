"""
Phase 05 — Semantic Enrichment Processor
"""

import re
import time
from collections import Counter
from .input_schema import Phase05Input
from .output_schema import Phase05Output


_DIALOGUE_VERBS = ("said", "asked", "replied", "shouted", "whispered", "cried", "murmured")
_THOUGHT_VERBS = ("thought", "wondered", "realized", "remembered", "felt", "imagined")
_EMOTION_HINTS = {
    "angry": ("angry", "furious", "rage"),
    "sad": ("cried", "tears", "sorrow", "grief"),
    "happy": ("smiled", "laugh", "joy", "glad"),
    "fear": ("afraid", "fear", "panic", "tremble"),
}


def _alias_to_character_id(character_registry: list[dict]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for character in character_registry:
        cid = character["character_id"]
        aliases = set(character.get("aliases", [])) | {character.get("canonical_name", "")}
        for alias in aliases:
            normalized = alias.strip().lower()
            if normalized:
                mapping[normalized] = cid
    return mapping


def _find_referenced_characters(text: str, alias_map: dict[str, str]) -> list[str]:
    lowered = text.lower()
    referenced = {
        cid for alias, cid in alias_map.items() if alias and re.search(rf"\b{re.escape(alias)}\b", lowered)
    }
    return sorted(referenced)


def _find_speaker_id(text: str, alias_map: dict[str, str]) -> tuple[str | None, float | None]:
    lowered = text.lower()
    for verb in _DIALOGUE_VERBS:
        for alias, cid in alias_map.items():
            if re.search(rf"\b{re.escape(alias)}\b\s+{verb}\b", lowered) or re.search(
                rf"\b{verb}\s+{re.escape(alias)}\b", lowered
            ):
                return cid, 0.9
    return (None, 0.45) if any(verb in lowered for verb in _DIALOGUE_VERBS) else (None, None)


def _find_thought_owner_id(text: str, alias_map: dict[str, str]) -> str | None:
    lowered = text.lower()
    if not any(verb in lowered for verb in _THOUGHT_VERBS):
        return None
    refs = _find_referenced_characters(text, alias_map)
    return refs[0] if refs else None


def _classify_primary_type(text: str, text_markers: list[str]) -> tuple[str, float]:
    lowered = text.lower()
    has_thought_verb = any(verb in lowered for verb in _THOUGHT_VERBS)
    if "double_quote" in text_markers:
        return "dialogue", 0.92
    if "single_quote" in text_markers and has_thought_verb:
        return "thought", 0.9
    if has_thought_verb:
        return "thought", 0.8
    if "single_quote" in text_markers:
        return "narration", 0.66
    if any(marker in text for marker in ('"', "“", "”")):
        return "dialogue", 0.82
    return "narration", 0.7


def _infer_emotion_tag(text: str) -> str | None:
    lowered = text.lower()
    for emotion, keywords in _EMOTION_HINTS.items():
        if any(keyword in lowered for keyword in keywords):
            return emotion
    return None


def _enrich_segment(segment: dict, alias_map: dict[str, str]) -> dict:
    text = segment.get("text", "")
    text_markers = segment.get("text_markers", [])
    primary_type, classification_confidence = _classify_primary_type(text, text_markers)
    refs = _find_referenced_characters(text, alias_map)

    speaker_id, speaker_confidence = _find_speaker_id(text, alias_map) if primary_type == "dialogue" else (None, None)
    thought_owner_id = _find_thought_owner_id(text, alias_map) if primary_type == "thought" else None

    pov_character_id = None
    if thought_owner_id:
        pov_character_id = thought_owner_id
    elif speaker_id and primary_type == "dialogue":
        pov_character_id = speaker_id

    return {
        "segment_id": segment.get("segment_id"),
        "primary_type": primary_type,
        "speaker_id": speaker_id,
        "thought_owner_id": thought_owner_id,
        "pov_character_id": pov_character_id,
        "referenced_characters": refs,
        "emotion_tag": _infer_emotion_tag(text),
        "classification_confidence": classification_confidence,
        "speaker_confidence": speaker_confidence,
    }


def process(input_data: Phase05Input) -> Phase05Output:
    start = time.time()

    alias_map = _alias_to_character_id(input_data.character_registry)
    enriched_segments = [_enrich_segment(segment, alias_map) for segment in input_data.segments]
    type_counts = dict(Counter(seg["primary_type"] for seg in enriched_segments))

    output = Phase05Output(
        enriched_segments=enriched_segments,
        character_registry=input_data.character_registry,
        enrichment_stats={
            "primary_type_counts": type_counts,
            "segments_with_speaker": sum(1 for seg in enriched_segments if seg["speaker_id"]),
            "segments_with_thought_owner": sum(
                1 for seg in enriched_segments if seg["thought_owner_id"]
            ),
            "average_classification_confidence": (
                sum(seg["classification_confidence"] for seg in enriched_segments) / len(enriched_segments)
                if enriched_segments
                else 0.0
            ),
        },
        meta={
            "phase": "05_semantic_enrichment",
            "version": "2.0.0",
            "timestamp": time.time(),
        },
        input_summary={
            "segment_count": len(input_data.segments),
            "character_count": len(input_data.character_registry),
        },
        output_summary={
            "enriched_count": len(enriched_segments),
        },
        errors=[],
        warnings=[],
        timings={"total_ms": (time.time() - start) * 1000},
    )

    return output
