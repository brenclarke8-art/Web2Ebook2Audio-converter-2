#!/usr/bin/env python3
"""
Character Voice Manager

Manages character-to-voice assignments for multi-voice audiobook generation.
Handles automatic voice assignment based on gender and manual overrides.
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from dialogue_detector import DialogueDetector
from kokoro_voice_catalog import KOKORO_VOICE_CATALOG

logger = logging.getLogger(__name__)


@dataclass
class CharacterVoiceAssignment:
    """Represents a character and their assigned voice"""
    character_name: str
    voice_name: str
    gender: Optional[str] = None
    dialogue_count: int = 0
    auto_assigned: bool = False


class CharacterVoiceManager:
    """Manages character voice assignments for multi-voice audiobooks"""

    VALID_GENDERS = {"male", "female", "neutral"}

    # Available Kokoro voices with gender information
    AVAILABLE_VOICES = KOKORO_VOICE_CATALOG

    def __init__(self, narrator_voice: str = 'af_heart',
                 default_male_voice: str = 'am_adam',
                 default_female_voice: str = 'af_bella',
                 auto_assign: bool = True,
                 enable_dialogue_llm: bool = False,
                 dialogue_llm_mode: str = "off",
                 dialogue_llm_model: str = 'mistral:instruct',
                 dialogue_llm_url: str = 'http://localhost:11434/api/chat',
                 dialogue_llm_timeout: int = 200,
                 dialogue_llm_strict_quotes: bool = False):
        """Initialize CharacterVoiceManager

        Args:
            narrator_voice: Voice to use for narration
            default_male_voice: Default voice for male characters
            default_female_voice: Default voice for female characters
            auto_assign: Whether to auto-assign voices based on gender
            enable_dialogue_llm: Deprecated; use dialogue_llm_mode instead.
                                  True is treated as dialogue_llm_mode="half".
            dialogue_llm_mode: Dialogue mode: "off", "half", "full", or "db_only"
            dialogue_llm_model: Ollama model name
            dialogue_llm_url: Ollama chat API URL
            dialogue_llm_timeout: Timeout for each Ollama request in seconds
            dialogue_llm_strict_quotes: If true, only double-quoted text can be
                                        classified as dialogue by LLM outputs.
        """
        logger.debug("Initializing CharacterVoiceManager")
        self.narrator_voice = narrator_voice
        self.default_male_voice = default_male_voice
        self.default_female_voice = default_female_voice
        self.auto_assign = auto_assign
        # Resolve effective mode: explicit dialogue_llm_mode wins; otherwise
        # fall back to the deprecated enable_dialogue_llm flag.
        if dialogue_llm_mode != "off":
            self.dialogue_llm_mode = dialogue_llm_mode
        elif enable_dialogue_llm:
            self.dialogue_llm_mode = "half"
        else:
            self.dialogue_llm_mode = "off"
        self.enable_dialogue_llm = (self.dialogue_llm_mode != "off")
        self.dialogue_llm_model = dialogue_llm_model
        self.dialogue_llm_url = dialogue_llm_url
        self.dialogue_llm_timeout = dialogue_llm_timeout
        self.dialogue_llm_strict_quotes = dialogue_llm_strict_quotes

        # Character assignments
        self.assignments: Dict[str, CharacterVoiceAssignment] = {}

        # Track which voices have been used (for variety)
        self.used_voices = set()

        logger.debug(f"CharacterVoiceManager initialized: narrator={narrator_voice}, auto_assign={auto_assign}")

    def analyze_and_assign_voices(
        self,
        text: str,
        known_characters: Optional[List[str]] = None,
        manual_mappings: Optional[Dict[str, str]] = None,
        known_character_records: Optional[List[Dict]] = None,
    ) -> Dict[str, CharacterVoiceAssignment]:
        """Analyze text, detect characters, and assign voices

        Args:
            text: Text to analyze
            known_characters: Optional list of known character names
            manual_mappings: Optional manual character-to-voice mappings
            known_character_records: Optional character DB records with authoritative
                gender values.

        Returns:
            Dictionary mapping character names to voice assignments
        """
        logger.info("Starting character voice analysis and assignment")
        if known_characters:
            known_character_names = sorted(
                name for name in known_characters
                if isinstance(name, str) and name
            )
            logger.debug("Known characters provided for assignment: %s", known_character_names)
        if manual_mappings:
            manual_mapping_names = sorted(
                name for name in manual_mappings
                if isinstance(name, str) and name
            )
            logger.debug("Manual voice mappings provided for: %s", manual_mapping_names)

        # Detect dialogue and characters
        detector = DialogueDetector(
            llm_mode=self.dialogue_llm_mode,
            llm_model=self.dialogue_llm_model,
            llm_url=self.dialogue_llm_url,
            llm_timeout=self.dialogue_llm_timeout,
            llm_strict_quotes=self.dialogue_llm_strict_quotes,
        )
        segments = detector.detect_dialogue_in_text(
            text,
            known_characters=known_characters,
            known_character_records=known_character_records,
        )
        logger.info(f"Detected {len(segments)} text segments")

        # Get characters with gender info
        characters_with_gender = detector.get_characters_with_gender()
        dialogue_counts = detector.get_character_dialogue_counts()

        gender_overrides: Dict[str, str] = {}
        for record in known_character_records or []:
            if not isinstance(record, dict):
                continue
            name = str(record.get("name", "")).strip()
            gender = str(record.get("gender", "")).strip().lower()
            if not name or gender not in self.VALID_GENDERS:
                continue
            gender_overrides[name.casefold()] = gender

        if gender_overrides:
            for char_name in list(characters_with_gender.keys()):
                override = gender_overrides.get(char_name.casefold())
                if override:
                    characters_with_gender[char_name] = override
            logger.info(
                "Applied character DB gender overrides for %d character(s)",
                sum(1 for name in characters_with_gender if name.casefold() in gender_overrides),
            )

        logger.info(f"Found {len(characters_with_gender)} characters")

        # Always assign narrator voice
        self.assignments['narrator'] = CharacterVoiceAssignment(
            character_name='narrator',
            voice_name=self.narrator_voice,
            gender=None,
            dialogue_count=dialogue_counts.get('narrator', 0),
            auto_assigned=False
        )
        self.used_voices.add(self.narrator_voice)

        # Assign voices to characters
        for char_name, gender in characters_with_gender.items():
            # Check if manual mapping exists
            if manual_mappings and char_name in manual_mappings:
                voice = manual_mappings[char_name]
                auto_assigned = False
                logger.info(f"Manual assignment: {char_name} -> {voice}")
            elif self.auto_assign:
                voice = self._auto_assign_voice(char_name, gender)
                auto_assigned = True
                logger.info(f"Auto-assigned: {char_name} ({gender}) -> {voice}")
            else:
                # No auto-assign and no manual mapping, use default
                voice = self.default_male_voice if gender == 'male' else self.default_female_voice
                auto_assigned = True
                logger.info(f"Default assignment: {char_name} -> {voice}")

            self.assignments[char_name] = CharacterVoiceAssignment(
                character_name=char_name,
                voice_name=voice,
                gender=gender,
                dialogue_count=dialogue_counts.get(char_name, 0),
                auto_assigned=auto_assigned
            )
            self.used_voices.add(voice)

        if manual_mappings:
            assigned_lookup = {name.casefold() for name in self.assignments}
            unused_manual = sorted(
                name for name in manual_mappings
                if isinstance(name, str) and name.casefold() not in assigned_lookup
            )
            if unused_manual:
                logger.warning(
                    "Manual voice mappings were configured for undetected characters: %s",
                    unused_manual,
                )

        logger.debug(
            "Final voice assignments: %s",
            {name: assignment.voice_name for name, assignment in sorted(self.assignments.items())},
        )
        logger.info(f"Voice assignment complete: {len(self.assignments)} characters assigned")
        return self.assignments

    def _auto_assign_voice(self, character_name: str, gender: Optional[str]) -> str:
        """Automatically assign a voice based on gender, trying to provide variety

        Args:
            character_name: Name of the character
            gender: Gender of the character ('male', 'female', 'neutral', or None)

        Returns:
            Voice name
        """
        # Get available voices for this gender
        if gender == 'male':
            available = [v for v, info in self.AVAILABLE_VOICES.items()
                        if info['gender'] == 'male']
        elif gender == 'female':
            available = [v for v, info in self.AVAILABLE_VOICES.items()
                        if info['gender'] == 'female']
        else:
            available = list(self.AVAILABLE_VOICES.keys())

        # Try to find an unused voice for variety
        unused = [v for v in available if v not in self.used_voices]
        if unused:
            # Prefer voices that are not the default
            non_default = [
                v for v in unused
                if v != self.default_male_voice
                and v != self.default_female_voice
                and v != self.narrator_voice
            ]
            if non_default:
                return non_default[0]
            non_narrator = [v for v in unused if v != self.narrator_voice]
            if non_narrator:
                return non_narrator[0]
            return unused[0]

        preferred_defaults = []
        if gender == 'male':
            preferred_defaults.append(self.default_male_voice)
        elif gender == 'female':
            preferred_defaults.append(self.default_female_voice)
        else:
            preferred_defaults.extend([self.default_female_voice, self.default_male_voice])

        for voice in preferred_defaults:
            if voice and voice != self.narrator_voice:
                return voice

        # All voices used, return a non-narrator fallback when possible
        non_narrator = [v for v in available if v != self.narrator_voice]
        if non_narrator:
            return non_narrator[0]
        for voice in sorted(self.AVAILABLE_VOICES):
            if voice != self.narrator_voice:
                return voice
        return self.narrator_voice

    def get_voice_for_character(self, character_name: str) -> str:
        """Get the assigned voice for a character

        Args:
            character_name: Name of the character

        Returns:
            Voice name
        """
        if character_name in self.assignments:
            return self.assignments[character_name].voice_name

        # Fallback to narrator voice if character not found
        logger.warning(f"Character '{character_name}' not found in assignments, using narrator voice")
        return self.narrator_voice

    def get_all_assigned_voices(self) -> List[str]:
        """Get list of all voices that have been assigned

        Returns:
            List of unique voice names
        """
        return list(self.used_voices)

    def generate_assignment_report(self) -> str:
        """Generate a human-readable report of voice assignments

        Returns:
            Formatted report string
        """
        report = ["Character Voice Assignments", "=" * 60, ""]

        # Sort by dialogue count
        sorted_assignments = sorted(
            self.assignments.values(),
            key=lambda a: a.dialogue_count,
            reverse=True
        )

        for assignment in sorted_assignments:
            auto_tag = " (auto)" if assignment.auto_assigned else " (manual)"
            gender_tag = f" [{assignment.gender}]" if assignment.gender else ""
            voice_desc = self.AVAILABLE_VOICES.get(assignment.voice_name, {}).get('description', '')

            report.append(f"Character: {assignment.character_name}{gender_tag}")
            report.append(f"  Voice: {assignment.voice_name}{auto_tag}")
            if voice_desc:
                report.append(f"  Description: {voice_desc}")
            report.append(f"  Dialogue instances: {assignment.dialogue_count}")
            report.append("")

        return "\n".join(report)

    def update_assignment(self, character_name: str, voice_name: str):
        """Manually update a character's voice assignment

        Args:
            character_name: Name of the character
            voice_name: New voice name
        """
        if character_name in self.assignments:
            old_voice = self.assignments[character_name].voice_name
            self.assignments[character_name].voice_name = voice_name
            self.assignments[character_name].auto_assigned = False
            self.used_voices.add(voice_name)
            logger.info(f"Updated assignment: {character_name} {old_voice} -> {voice_name}")
        else:
            logger.warning(f"Cannot update: character '{character_name}' not found")

    @classmethod
    def get_available_voices_by_gender(cls, gender: str) -> List[str]:
        """Get list of available voices for a specific gender

        Args:
            gender: 'male' or 'female'

        Returns:
            List of voice names
        """
        return [v for v, info in cls.AVAILABLE_VOICES.items()
                if info['gender'] == gender]


# Example usage
if __name__ == '__main__':
    # Example text with dialogue
    sample_text = """
    Alice walked into the room, looking around nervously.
    "Hello?" she called out. "Is anyone here?"
    Bob emerged from the shadows. "I've been waiting for you," he said with a smile.
    "You scared me!" Alice exclaimed, her hand on her chest.
    Bob laughed. "Sorry about that. I didn't mean to frighten you."
    They sat down at the table, and Alice began to explain her plan.
    "We need to move quickly," she said. "Time is running out."
    "I understand," Bob replied. "When do we leave?"
    "Tomorrow at dawn," Alice answered. "Be ready."
    """

    # Create manager
    manager = CharacterVoiceManager()

    # Analyze and assign voices
    assignments = manager.analyze_and_assign_voices(sample_text)

    # Display report
    print(manager.generate_assignment_report())

    # Get voice for specific character
    print("\nVoice lookups:")
    print(f"  Alice's voice: {manager.get_voice_for_character('Alice')}")
    print(f"  Bob's voice: {manager.get_voice_for_character('Bob')}")
    print(f"  Narrator's voice: {manager.get_voice_for_character('narrator')}")

    # List all assigned voices
    print(f"\nAll assigned voices: {manager.get_all_assigned_voices()}")
