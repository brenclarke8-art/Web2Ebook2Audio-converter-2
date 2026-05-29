from __future__ import annotations
from typing import Dict, Optional


class VoiceRouter:
    """
    Centralized voice routing logic.

    Responsibilities:
    - Map character names → assigned voices
    - Fall back to gender-based defaults
    - Fall back to narrator voice
    - Allow segment-type overrides (dialogue, thought, narration)
    """

    def __init__(
        self,
        *,
        character_voices: Optional[Dict[str, str]] = None,
        default_male_voice: str = "am_adam",
        default_female_voice: str = "af_heart",
        narrator_voice: str = "af_heart",
        thought_voice: Optional[str] = None,
        system_voice: Optional[str] = None,
    ):
        self.character_voices = character_voices or {}
        self.default_male_voice = default_male_voice
        self.default_female_voice = default_female_voice
        self.narrator_voice = narrator_voice
        self.thought_voice = thought_voice or narrator_voice
        self.system_voice = system_voice or narrator_voice

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_voice_for_segment(
        self,
        *,
        speaker: str,
        seg_type: str,
        gender: str = "unknown",
    ) -> str:
        """
        Determine the correct voice for a segment.

        Priority:
        1. Character-specific voice
        2. Segment-type override (thought/system)
        3. Gender-based default
        4. Narrator fallback
        """

        speaker_norm = speaker.strip().lower()

        # 1. Character-specific voice
        if speaker_norm in self.character_voices:
            return self.character_voices[speaker_norm]

        # 2. Segment-type overrides
        if seg_type == "thought":
            return self.thought_voice
        if seg_type == "system":
            return self.system_voice

        # 3. Gender-based fallback
        gender_norm = gender.strip().lower()
        if gender_norm == "male":
            return self.default_male_voice
        if gender_norm == "female":
            return self.default_female_voice

        # 4. Narrator fallback
        return self.narrator_voice

    # ------------------------------------------------------------------
    # Character voice assignment
    # ------------------------------------------------------------------

    def assign_voice(self, character: str, voice: str) -> None:
        """Assign a voice to a character."""
        self.character_voices[character.strip().lower()] = voice

    def remove_character(self, character: str) -> None:
        """Remove a character-specific voice assignment."""
        self.character_voices.pop(character.strip().lower(), None)

    def clear(self) -> None:
        """Remove all character-specific assignments."""
        self.character_voices.clear()
