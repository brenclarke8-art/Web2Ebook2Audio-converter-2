# src/ebook_app/pipeline/chapter_rebuilder.py
"""
Chapter Rebuilder
-----------------
Takes Pass‑2 classified segments and produces the final chapter structure.
"""

from __future__ import annotations
from typing import List, Dict


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
        # voice_router is optional; voices are assigned later in TTS
        self.voice_router = voice_router

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rebuild_chapter(
        self,
        chapter_id: str,
        title: str,
        pass2_segments: List[Dict],
        character_db: List[Dict],
    ) -> Dict:
        """
        Build the final chapter structure.
        """
        final_segments: List[Dict] = []
        final_chars_map: Dict[str, Dict] = {}

        for seg in pass2_segments:
            speaker = str(seg.get("speaker", "")).strip()
            gender = str(seg.get("gender", "unknown")).lower()
            norm = normalize_name(speaker) if speaker else ""

            # Track characters for final output (but do NOT mutate DB)
            if speaker and norm:
                # Find canonical entry
                entry = next(
                    (c for c in character_db if normalize_name(c.get("name", "")) == norm),
                    None,
                )
                if entry:
                    final_chars_map[norm] = {
                        "name": entry["name"],
                        "gender": entry["gender"],
                        "voice": entry.get("voice", ""),
                    }
                else:
                    # Character not in DB (rare) — include minimal info
                    final_chars_map[norm] = {
                        "name": speaker,
                        "gender": gender,
                        "voice": "",
                    }

            # Build final segment dict (NO voice assignment here)
            final_segments.append(
                {
                    "text": seg.get("text", ""),
                    "type": seg.get("type", "narration"),
                    "speaker": speaker,
                    "gender": gender,
                    "speaker_confidence": float(seg.get("speaker_confidence", 0.0)),
                    "gender_confidence": float(seg.get("gender_confidence", 0.0)),
                    "character_confidence": float(seg.get("character_confidence", 0.0)),
                    "paragraph_id": int(seg.get("paragraph_id", -1)),
                    # voice is assigned later in TTS or controller
                }
            )

        return {
            "chapter_id": chapter_id,
            "title": title,
            "segments": final_segments,
            "characters": list(final_chars_map.values()),
        }
