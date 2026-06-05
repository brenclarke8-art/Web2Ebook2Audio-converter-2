# src/ebook_app/pipeline/voice_router.py
"""
Voice Router with alias matching.
"""

from __future__ import annotations
from typing import List, Dict


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
        - character DB (with alias support)
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_voice_for_segment(
        self,
        segment: Dict,
        character_db: List[Dict],
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

        # Thought segments → narrator voice (optional improvement)
        if seg_type == "thought":
            return self.narrator_voice

        # Narration / unknown speaker → narrator voice
        if not speaker or speaker.lower() in {"narrator", "unknown"}:
            return self.narrator_voice

        norm = _normalize_name(speaker)

        # ------------------------------------------------------------------
        # Alias matching
        # ------------------------------------------------------------------
        for c in character_db:
            cname = str(c.get("name", "") or "").strip()
            if not cname:
                continue

            # Normalize canonical name
            if _normalize_name(cname) == norm:
                voice = str(c.get("voice", "") or "").strip()
                if voice:
                    return voice

            # Check aliases
            aliases = c.get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    if _normalize_name(alias) == norm:
                        voice = str(c.get("voice", "") or "").strip()
                        if voice:
                            return voice

        # ------------------------------------------------------------------
        # Fallback by gender
        # ------------------------------------------------------------------
        if gender == "male":
            return self.default_male_voice
        if gender == "female":
            return self.default_female_voice

        # Final fallback
        return self.narrator_voice
