"""
Phase 04 — Character Registry Processor
"""

import re
import time
from collections import defaultdict
from .input_schema import Phase04Input
from .output_schema import Phase04Output


_NAME_PATTERN = re.compile(r"\b(?:Mr\.?|Mrs\.?|Ms\.?|Miss\.?|Dr\.?)?\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b")
_GENERIC_TOKENS = {
    "The",
    "A",
    "An",
    "Chapter",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
}
_TITLE_GENDER = {"mr": "male", "mrs": "female", "ms": "female", "miss": "female"}


def _clean_alias(alias: str) -> str:
    return re.sub(r"\s+", " ", alias.strip(" ,.;:!?\"'()[]{}"))


def _canonical_key(alias: str) -> str:
    parts = [p for p in _clean_alias(alias).split() if p]
    if not parts:
        return ""
    if parts[0].rstrip(".").lower() in _TITLE_GENDER:
        parts = parts[1:]
    return " ".join(parts)


def _extract_character_mentions(text: str) -> list[str]:
    aliases = []
    for match in _NAME_PATTERN.findall(text):
        alias = _clean_alias(match)
        if not alias:
            continue
        parts = alias.split()
        core = parts[-1]
        if core in _GENERIC_TOKENS:
            continue
        aliases.append(alias)
    return aliases


def _build_character_registry(segments: list[dict]) -> list[dict]:
    canonical_aliases: dict[str, set[str]] = defaultdict(set)
    canonical_counts: dict[str, int] = defaultdict(int)
    canonical_gender: dict[str, str | None] = defaultdict(lambda: None)

    for segment in segments:
        for alias in _extract_character_mentions(segment.get("text", "")):
            canonical = _canonical_key(alias)
            if not canonical:
                continue
            canonical_aliases[canonical].add(alias)
            canonical_counts[canonical] += 1
            title = alias.split()[0].rstrip(".").lower()
            if canonical_gender[canonical] is None and title in _TITLE_GENDER:
                canonical_gender[canonical] = _TITLE_GENDER[title]

    ordered_canonical = sorted(
        canonical_counts.keys(), key=lambda name: (-canonical_counts[name], name.lower())
    )

    registry = []
    for idx, canonical in enumerate(ordered_canonical, start=1):
        aliases = sorted(canonical_aliases[canonical])
        if canonical not in aliases:
            aliases.insert(0, canonical)

        registry.append(
            {
                "character_id": f"char_{idx:03d}",
                "canonical_name": canonical,
                "aliases": aliases,
                "gender": canonical_gender[canonical],
                "importance": "major" if canonical_counts[canonical] >= 2 else "minor",
            }
        )

    return registry


def process(input_data: Phase04Input) -> Phase04Output:
    start = time.time()

    registry = _build_character_registry(input_data.segments)

    output = Phase04Output(
        character_registry=registry,
        segments=input_data.segments,
        meta={
            "phase": "04_character_registry",
            "version": "1.0.0",
            "timestamp": time.time(),
        },
        input_summary={
            "segment_count": len(input_data.segments),
        },
        output_summary={
            "character_count": len(registry),
            "segment_count": len(input_data.segments),
        },
        errors=[],
        warnings=[],
        timings={"total_ms": (time.time() - start) * 1000},
    )

    return output
