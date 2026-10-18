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


def _find_speaker_id(text: str, alias_map: dict[str, str]) -> str | None:
    lowered = text.lower()
    for verb in _DIALOGUE_VERBS:
        for alias, cid in alias_map.items():
            if re.search(rf"\b{re.escape(alias)}\b\s+{verb}\b", lowered) or re.search(
                rf"{verb}\s+\b{re.escape(alias)}\b", lowered
            ):
                return cid
    refs = _find_referenced_characters(text, alias_map)
    return refs[0] if refs else None


def _find_thought_owner_id(text: str, alias_map: dict[str, str]) -> str | None:
    lowered = text.lower()
    if not any(verb in lowered for verb in _THOUGHT_VERBS):
        return None
    refs = _find_referenced_characters(text, alias_map)
    return refs[0] if refs else None


def _classify_segment_type(text: str) -> str:
    lowered = text.lower()
    if any(marker in text for marker in ('"', "“", "”")):
        return "dialogue"
    if any(verb in lowered for verb in _THOUGHT_VERBS):
        return "thought"
    return "narration"


def _confidence(segment_type: str, speaker_id: str | None, thought_owner_id: str | None, refs: list[str]) -> float:
    if segment_type == "dialogue" and speaker_id:
        return 0.95
    if segment_type == "thought" and thought_owner_id:
        return 0.9
    if refs:
        return 0.78
    return 0.65


def _enrich_segment(segment: dict, alias_map: dict[str, str]) -> dict:
    text = segment.get("text", "")
    segment_type = _classify_segment_type(text)
    refs = _find_referenced_characters(text, alias_map)

    speaker_id = _find_speaker_id(text, alias_map) if segment_type == "dialogue" else None
    thought_owner_id = _find_thought_owner_id(text, alias_map) if segment_type == "thought" else None

    return {
        "segment_id": segment.get("segment_id"),
        "text": text,
        "segment_type": segment_type,
        "speaker_id": speaker_id,
        "thought_owner_id": thought_owner_id,
        "referenced_characters": refs,
        "confidence": _confidence(segment_type, speaker_id, thought_owner_id, refs),
    }


def process(input_data: Phase05Input) -> Phase05Output:
    start = time.time()

    alias_map = _alias_to_character_id(input_data.character_registry)
    enriched_segments = [_enrich_segment(segment, alias_map) for segment in input_data.segments]
    type_counts = dict(Counter(seg["segment_type"] for seg in enriched_segments))

    output = Phase05Output(
        enriched_segments=enriched_segments,
        character_registry=input_data.character_registry,
        enrichment_stats={
            "segment_type_counts": type_counts,
            "segments_with_speaker": sum(1 for seg in enriched_segments if seg["speaker_id"]),
            "segments_with_thought_owner": sum(
                1 for seg in enriched_segments if seg["thought_owner_id"]
            ),
            "average_confidence": (
                sum(seg["confidence"] for seg in enriched_segments) / len(enriched_segments)
                if enriched_segments
                else 0.0
            ),
        },
        meta={
            "phase": "05_semantic_enrichment",
            "version": "1.0.0",
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
