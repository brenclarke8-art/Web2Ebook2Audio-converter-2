# src/ebook_app/pipeline/chapter_rebuilder.py
from __future__ import annotations
from typing import List, Dict
from ebook_app.models.character_db import CharacterDatabase


def normalize_name(name: str) -> str:
    if not name:
        return ""
    return (
        name.strip()
            .lower()
            .replace(".", "")
            .replace(",", "")
            .replace("  ", " ")
    )


class ChapterRebuilder:
    """
    Rebuilds a chapter from Pass‑2 segments into final TTS/EPUB-ready format.
    """

    def __init__(self, voice_router=None):
        self.voice_router = voice_router

    def rebuild_chapter(
        self,
        chapter_id: str,
        title: str,
        pass2_segments: List[Dict],
        character_db: CharacterDatabase,
    ) -> Dict:
        final_segments: List[Dict] = []
        final_chars_map: Dict[str, Dict] = {}

        for seg in pass2_segments:
            speaker = str(seg.get("speaker", "")).strip()
            gender = str(seg.get("gender", "unknown")).lower()
            norm = normalize_name(speaker) if speaker else ""

            # Character lookup using CharacterDatabase
            entry = character_db.get(speaker) if speaker else None

            if entry:
                final_chars_map[norm] = {
                    "name": entry.name,
                    "gender": entry.gender,
                    "voice": entry.voice,
                }
            elif speaker:
                final_chars_map[norm] = {
                    "name": speaker,
                    "gender": gender,
                    "voice": "",
                }

            # Build final segment (preserve all Pass‑2 fields)
            final_segments.append(
                {
                    "text": seg.get("text", ""),
                    "type": seg.get("type", "narration"),
                    "speaker": speaker,
                    "gender": gender,
                    "speaker_confidence": float(seg.get("speaker_confidence", 0.0)),
                    "gender_confidence": float(seg.get("gender_confidence", 0.0)),
                    "character_confidence": float(seg.get("character_confidence", 0.0)),
                    "paragraph_id": seg.get("paragraph_id", ""),
                    "segment_id": seg.get("segment_id", ""),
                    "context_before": seg.get("context_before", ""),
                    "context_after": seg.get("context_after", ""),
                    "is_dialogue_candidate": seg.get("is_dialogue_candidate", False),
                }
            )

        return {
            "chapter_id": chapter_id,
            "title": title,
            "segments": final_segments,
            "characters": list(final_chars_map.values()),
        }
