# src/ebook_app/models/character_db.py
"""In-memory character database used for multi-speaker TTS assignment."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

@dataclass
class Character:
    """Represents a named character and their assigned TTS voice.

    :param name:        Character's name as it appears in the text.
    :param voice:       Kokoro voice identifier assigned to this character.
    :param gender:      Optional inferred or user-defined gender label.
    :param description: Optional short description (e.g. archetype).
    """

    name: str
    voice: str
    gender: str = "unknown"
    description: str = ""


class CharacterDatabase:
    """Manages a registry of :class:`Character` objects.

    Usage::

        db = CharacterDatabase()
        db.add(Character(name="Elena", voice="af_heart"))
        char = db.get("Elena")

    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._chars: dict[str, Character] = {}
        self.path = Path(path) if path else None
        if self.path and self.path.exists():
            self.load()

    def add(self, character: Character) -> None:
        """Register a character (overwrites if the name already exists)."""
        self._chars[character.name] = character
        self._save_if_configured()

    def get(self, name: str) -> Character | None:
        """Return the :class:`Character` for *name*, or ``None``."""
        return self._chars.get(name)

    def all(self) -> list[Character]:
        """Return all registered characters."""
        return list(self._chars.values())

    def remove(self, name: str) -> None:
        """Remove the character with *name*, silently if not found."""
        self._chars.pop(name, None)
        self._save_if_configured()

    def __len__(self) -> int:
        return len(self._chars)

    def to_list(self) -> list[dict]:
        """Serialize all characters to a list of dictionaries."""
        return [
            {
                "name": char.name,
                "voice": char.voice,
                "gender": char.gender,
                "description": char.description,
            }
            for char in self.all()
        ]

    def load(self) -> None:
        """Load character entries from configured JSON path."""
        if not self.path:
            return

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            payload = []

        self._chars = {}
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict) or not item.get("name"):
                    continue
                self._chars[item["name"]] = Character(
                    name=item["name"],
                    voice=item.get("voice", ""),
                    gender=item.get("gender", "unknown"),
                    description=item.get("description", ""),
                )

    def save(self) -> None:
        """Persist character entries to configured JSON path."""
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.to_list(), indent=2), encoding="utf-8")

    def _save_if_configured(self) -> None:
        if self.path:
            self.save()
