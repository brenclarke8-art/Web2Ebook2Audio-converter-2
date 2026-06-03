# src/ebook_app/models/character_db.py
"""In-memory character database used for multi-speaker TTS assignment."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import json
from pathlib import Path
import re


_TRAILING_PUNCTUATION = ".,!?;:"
_HONORIFICS = {
    "mr",
    "mrs",
    "ms",
    "miss",
    "dr",
    "sir",
    "lady",
    "lord",
    "captain",
}


def normalize_character_name(name: str, *, strip_title: bool = False) -> str:
    """Return a conservative normalized key for character matching."""
    cleaned = " ".join((name or "").strip().split())
    while cleaned and cleaned[-1] in _TRAILING_PUNCTUATION:
        cleaned = cleaned[:-1].rstrip()

    if strip_title:
        parts = cleaned.split(" ")
        if len(parts) > 1:
            head = parts[0].rstrip(".").casefold()
            if head in _HONORIFICS:
                cleaned = " ".join(parts[1:]).strip()

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.casefold()

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
    aliases: list[str] = field(default_factory=list)


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

    def resolve_name(
        self,
        name: str,
        *,
        allow_fuzzy: bool = True,
        min_fuzzy_score: float = 0.92,
    ) -> Character | None:
        """Resolve a raw name to a canonical character using deterministic matching first."""
        raw = (name or "").strip()
        if not raw:
            return None

        direct = self.get(raw)
        if direct:
            return direct

        folded = raw.casefold()
        for canonical, char in self._chars.items():
            if canonical.casefold() == folded:
                return char
            if any(alias.casefold() == folded for alias in char.aliases):
                return char

        raw_keys = self._normalized_keys(raw)
        for canonical, char in self._chars.items():
            candidate_keys = self._normalized_keys(canonical)
            for alias in char.aliases:
                candidate_keys.update(self._normalized_keys(alias))
            if raw_keys & candidate_keys:
                return char

        if not allow_fuzzy or not raw_keys:
            return None

        best: tuple[float, Character] | None = None
        second_best = 0.0
        for canonical, char in self._chars.items():
            candidate_keys = self._normalized_keys(canonical)
            for alias in char.aliases:
                candidate_keys.update(self._normalized_keys(alias))
            for left in raw_keys:
                for right in candidate_keys:
                    score = SequenceMatcher(a=left, b=right).ratio()
                    if best is None or score > best[0]:
                        second_best = best[0] if best else 0.0
                        best = (score, char)
                    elif score > second_best:
                        second_best = score

        if best and best[0] >= min_fuzzy_score and (best[0] - second_best) >= 0.02:
            return best[1]
        return None

    def merge_alias(self, canonical_name: str, alias: str) -> bool:
        """Attach *alias* to *canonical_name* if it is a distinct variant."""
        char = self.get(canonical_name)
        alias_clean = " ".join((alias or "").strip().split())
        if not char or not alias_clean:
            return False
        if normalize_character_name(alias_clean) == normalize_character_name(char.name):
            return False
        if any(normalize_character_name(existing) == normalize_character_name(alias_clean) for existing in char.aliases):
            return False
        char.aliases.append(alias_clean)
        self._save_if_configured()
        return True

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
                "aliases": list(char.aliases),
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
                    aliases=self._normalize_aliases(item.get("aliases", [])),
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

    @staticmethod
    def _normalize_aliases(raw: object) -> list[str]:
        if not isinstance(raw, list):
            return []
        out: list[str] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, str):
                continue
            alias = " ".join(item.strip().split())
            if not alias:
                continue
            key = normalize_character_name(alias)
            if key in seen:
                continue
            seen.add(key)
            out.append(alias)
        return out

    @staticmethod
    def _normalized_keys(name: str) -> set[str]:
        keys = {normalize_character_name(name)}
        with_title_stripped = normalize_character_name(name, strip_title=True)
        if with_title_stripped:
            keys.add(with_title_stripped)
        keys.discard("")
        return keys
