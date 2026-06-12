# ebook_app/tts/voice_router.py
"""
Voice Router with CharacterDatabase integration.
"""

from __future__ import annotations
from typing import Dict
from ebook_app.app.state.character_db import CharacterDatabase


def _normalize_name(name: str) -> str:
    if not name:
        return ""
    return (
        name.strip()
            .lower()
            .replace(".", "")
            .replace(",", "")
            .replace("  ", " ")
    )


class VoiceRouter:
    """
    Voice routing based on:
        - segment type
        - speaker name
        - gender
        - CharacterDatabase (canonical + alias + fuzzy)
        - global defaults
    """

    def __init__(
        self,
        narrator_voice: str,
        default_male_voice: str,
        default_female_voice: str,
    ) -> None:
        self.narrator_voice = narrator_voice
        self.default_male_voice = default_male_voice
        self.default_female_voice = default_female_voice

    def get_voice_for_segment(
        self,
        segment: Dict,
        character_db: CharacterDatabase,
    ) -> str:
        """
        Decide which voice to use for a given segment.
        """

        # Respect pre-assigned voice
        existing_voice = segment.get("voice")
        if isinstance(existing_voice, str) and existing_voice.strip():
            return existing_voice.strip()

        seg_type = str(segment.get("type", "narration") or "narration").lower()
        speaker = str(segment.get("speaker", "") or "").strip()
        gender = str(segment.get("gender", "unknown") or "unknown").lower()

        # Thought → narrator voice
        if seg_type == "thought":
            return self.narrator_voice

        # Narration / unknown speaker → narrator voice
        if not speaker or speaker.lower() in {"narrator", "unknown"}:
            return self.narrator_voice

        # ------------------------------------------------------------------
        # CharacterDatabase lookup (canonical + alias + fuzzy)
        # ------------------------------------------------------------------
        entry = character_db.get(speaker)
        if entry and entry.voice:
            return entry.voice

        # ------------------------------------------------------------------
        # Fallback by gender
        # ------------------------------------------------------------------
        if gender == "male":
            return self.default_male_voice
        if gender == "female":
            return self.default_female_voice

        # Final fallback
        return self.narrator_voice
