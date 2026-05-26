# src/ebook_app/models/character_db.py
"""In-memory character database used for multi-speaker TTS assignment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Character:
    """Represents a named character and their assigned TTS voice.

    :param name:        Character's name as it appears in the text.
    :param voice:       Kokoro voice identifier assigned to this character.
    :param description: Optional short description (e.g. gender, archetype).
    """

    name: str
    voice: str
    description: str = ""


class CharacterDatabase:
    """Manages a registry of :class:`Character` objects.

    Usage::

        db = CharacterDatabase()
        db.add(Character(name="Elena", voice="af_heart"))
        char = db.get("Elena")

    TODO: persist to / load from JSON alongside the project file.
    """

    def __init__(self) -> None:
        self._chars: dict[str, Character] = {}

    def add(self, character: Character) -> None:
        """Register a character (overwrites if the name already exists)."""
        self._chars[character.name] = character

    def get(self, name: str) -> Optional[Character]:
        """Return the :class:`Character` for *name*, or ``None``."""
        return self._chars.get(name)

    def all(self) -> list[Character]:
        """Return all registered characters."""
        return list(self._chars.values())

    def remove(self, name: str) -> None:
        """Remove the character with *name*, silently if not found."""
        self._chars.pop(name, None)

    def __len__(self) -> int:
        return len(self._chars)
