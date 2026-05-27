from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, Optional


@dataclass(frozen=True)
class VoiceResolution:
    requested_speaker: str
    matched_speaker: str
    voice: str
    resolution: str


def _normalize_speaker_key(speaker: Optional[str]) -> Optional[str]:
    if not isinstance(speaker, str):
        return None
    cleaned = speaker.strip()
    return cleaned.casefold() if cleaned else None


def build_normalized_voice_lookup(voice_mappings: Dict[str, str]) -> Dict[str, str]:
    return {
        key.strip().casefold(): key
        for key in voice_mappings
        if isinstance(key, str) and key.strip()
    }


def resolve_voice_mapping(
    speaker: Optional[str],
    voice_mappings: Dict[str, str],
    narrator_voice: str = "af_heart",
    normalized_lookup: Optional[Dict[str, str]] = None,
) -> VoiceResolution:
    fallback_voice = voice_mappings.get("narrator", narrator_voice)
    normalized_speaker = _normalize_speaker_key(speaker)
    requested_speaker = speaker.strip() if isinstance(speaker, str) and speaker.strip() else "narrator"

    if normalized_speaker is None:
        return VoiceResolution(
            requested_speaker=requested_speaker,
            matched_speaker="narrator",
            voice=fallback_voice,
            resolution="empty-speaker",
        )

    if speaker in voice_mappings:
        return VoiceResolution(
            requested_speaker=requested_speaker,
            matched_speaker=speaker,
            voice=voice_mappings[speaker],
            resolution="exact",
        )

    normalized_lookup = normalized_lookup or build_normalized_voice_lookup(voice_mappings)
    matched_key = normalized_lookup.get(normalized_speaker)
    if matched_key is not None:
        return VoiceResolution(
            requested_speaker=requested_speaker,
            matched_speaker=matched_key,
            voice=voice_mappings[matched_key],
            resolution="normalized-speaker",
        )

    return VoiceResolution(
        requested_speaker=requested_speaker,
        matched_speaker="narrator",
        voice=fallback_voice,
        resolution="fallback-to-narrator",
    )


def build_multispeaker_debug_report(
    output_name: str,
    assignments: Dict[str, object],
    voice_mappings: Dict[str, str],
    chapter_segments: Iterable[Iterable[object]],
    chapter_titles: Iterable[str],
    manual_mappings: Optional[Dict[str, str]] = None,
    narrator_voice: str = "af_heart",
) -> str:
    lines = [
        "Multi-Speaker Debug Report",
        "=" * 60,
        f"Book: {output_name}",
        f"Narrator voice: {voice_mappings.get('narrator', narrator_voice)}",
        "",
        "Voice Assignments",
        "-" * 60,
    ]

    for character_name, assignment in sorted(
        assignments.items(),
        key=lambda item: (-getattr(item[1], "dialogue_count", 0), item[0]),
    ):
        gender = getattr(assignment, "gender", None) or "unknown"
        source = "auto" if getattr(assignment, "auto_assigned", False) else "manual"
        lines.append(
            f"- {character_name}: voice={getattr(assignment, 'voice_name', narrator_voice)}, "
            f"source={source}, gender={gender}, dialogue_count={getattr(assignment, 'dialogue_count', 0)}"
        )

    duplicate_voice_counts = Counter(voice_mappings.values())
    shared_voices = {
        voice: count
        for voice, count in sorted(duplicate_voice_counts.items())
        if count > 1
    }
    lines.extend(["", "Shared Voices", "-" * 60])
    if shared_voices:
        for voice, count in shared_voices.items():
            owners = sorted(name for name, mapped_voice in voice_mappings.items() if mapped_voice == voice)
            lines.append(f"- {voice}: used by {count} speakers ({', '.join(owners)})")
    else:
        lines.append("- None")

    manual_mappings = manual_mappings or {}
    assigned_lookup = {
        assigned_name.casefold()
        for assigned_name in assignments
        if isinstance(assigned_name, str)
    }
    unused_manual = sorted(
        name for name in manual_mappings
        if isinstance(name, str) and name.casefold() not in assigned_lookup
    )
    lines.extend(["", "Unused Manual Mappings", "-" * 60])
    if unused_manual:
        for name in unused_manual:
            lines.append(f"- {name}: configured_voice={manual_mappings[name]}")
    else:
        lines.append("- None")

    lines.extend(["", "Chapter Resolution Summary", "-" * 60])
    normalized_lookup = build_normalized_voice_lookup(voice_mappings)
    for chapter_index, (title, segments) in enumerate(zip(chapter_titles, chapter_segments), start=1):
        segment_list = list(segments)
        dialogue_segments = [segment for segment in segment_list if getattr(segment, "is_dialogue", False)]
        voice_counts = Counter()
        fallback_counts = Counter()
        fallback_examples = []

        for seg_index, segment in enumerate(dialogue_segments, start=1):
            resolution = resolve_voice_mapping(
                getattr(segment, "speaker", None),
                voice_mappings,
                narrator_voice=narrator_voice,
                normalized_lookup=normalized_lookup,
            )
            voice_counts[(resolution.matched_speaker, resolution.voice)] += 1
            if resolution.resolution != "exact":
                fallback_counts[resolution.resolution] += 1
                if len(fallback_examples) < 5:
                    fallback_examples.append(
                        f"  * segment {seg_index}: requested='{resolution.requested_speaker}', "
                        f"matched='{resolution.matched_speaker}', voice='{resolution.voice}', "
                        f"reason={resolution.resolution}"
                    )

        lines.append(
            f"- Chapter {chapter_index}: {title} | total_segments={len(segment_list)} "
            f"| dialogue_segments={len(dialogue_segments)} | unique_dialogue_voices={len(voice_counts)}"
        )
        if voice_counts:
            for (speaker_name, voice_name), count in sorted(
                voice_counts.items(),
                key=lambda item: (-item[1], item[0][0], item[0][1]),
            ):
                lines.append(f"    - speaker={speaker_name}, voice={voice_name}, segments={count}")
        else:
            lines.append("    - No dialogue-like segments detected")

        if fallback_counts:
            lines.append(
                "    - Non-exact resolutions: "
                + ", ".join(f"{reason}={count}" for reason, count in sorted(fallback_counts.items()))
            )
            lines.extend(fallback_examples)

    return "\n".join(lines) + "\n"
