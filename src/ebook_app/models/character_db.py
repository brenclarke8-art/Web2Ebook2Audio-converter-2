# src/ebook_app/models/character_db.py
"""
Character Database
------------------
Persistent storage for character metadata:
    - canonical name
    - gender
    - voice assignment
    - aliases
    - description (optional)

Supports:
    - canonical lookup
    - alias lookup
    - fuzzy matching
    - merging
    - JSON load/save
"""

from __future__ import annotations
import json
import difflib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional


# ------------------------------------------------------------
# Normalization helper
# ------------------------------------------------------------

def normalize_character_name(name: str) -> str:
    if not name:
        return ""
    return (
        name.strip()
            .lower()
            .replace(".", "")
            .replace(",", "")
            .replace("  ", " ")
    )


# ------------------------------------------------------------
# Character model
# ------------------------------------------------------------

@dataclass
class Character:
    name: str
    gender: str = "unknown"
    voice: str = ""
    aliases: List[str] = None
    description: str = ""

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "gender": self.gender,
            "voice": self.voice,
            "aliases": self.aliases or [],
            "description": self.description,
        }

    @staticmethod
    def from_dict(data: Dict) -> "Character":
        return Character(
            name=data.get("name", ""),
            gender=data.get("gender", "unknown"),
            voice=data.get("voice", ""),
            aliases=list(data.get("aliases", [])),
            description=data.get("description", ""),
        )


# ------------------------------------------------------------
# Character Database
# ------------------------------------------------------------

class CharacterDatabase:
    """
    Persistent character database with:
        - canonical lookup
        - alias lookup
        - fuzzy matching
        - merging
        - JSON load/save
    """

    def __init__(self, path: Optional[Path] = None):
        self.path: Optional[Path] = path
        self._chars: Dict[str, Character] = {}

        if self.path and self.path.exists():
            self.load()

    # --------------------------------------------------------
    # Persistence
    # --------------------------------------------------------

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._chars = {
                normalize_character_name(entry["name"]): Character.from_dict(entry)
                for entry in data
            }
        except Exception:
            self._chars = {}

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [c.to_dict() for c in self._chars.values()]
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # --------------------------------------------------------
    # Lookup
    # --------------------------------------------------------

    def get(self, name: str) -> Optional[Character]:
        """
        Lookup by:
            1. canonical name
            2. alias match
            3. fuzzy match
        """
        if not name:
            return None

        norm = normalize_character_name(name)

        # 1. Canonical match
        if norm in self._chars:
            return self._chars[norm]

        # 2. Alias match
        for c in self._chars.values():
            for alias in c.aliases or []:
                if normalize_character_name(alias) == norm:
                    return c

        # 3. Fuzzy match
        all_names = list(self._chars.keys())
        if all_names:
            best = difflib.get_close_matches(norm, all_names, n=1, cutoff=0.85)
            if best:
                return self._chars[best[0]]

        return None

    # --------------------------------------------------------
    # Add / Update
    # --------------------------------------------------------

    def add_or_update(
        self,
        name: str,
        gender: str = "unknown",
        voice: str = "",
        aliases: Optional[List[str]] = None,
        description: str = "",
    ) -> Character:
        norm = normalize_character_name(name)
        if norm in self._chars:
            c = self._chars[norm]
            c.gender = gender or c.gender
            c.voice = voice or c.voice
            if aliases:
                c.aliases = list(set((c.aliases or []) + aliases))
            if description:
                c.description = description
            return c

        c = Character(
            name=name,
            gender=gender,
            voice=voice,
            aliases=aliases or [],
            description=description,
        )
        self._chars[norm] = c
        return c

    # --------------------------------------------------------
    # Merge characters
    # --------------------------------------------------------

    def merge(self, primary_name: str, secondary_name: str) -> None:
        """
        Merge secondary into primary:
            - combine aliases
            - preserve voice if primary has none
            - remove secondary
        """
        primary = self.get(primary_name)
        secondary = self.get(secondary_name)

        if not primary or not secondary or primary is secondary:
            return

        # Merge aliases
        primary.aliases = list(set((primary.aliases or []) +
                                   (secondary.aliases or []) +
                                   [secondary.name]))

        # Merge voice
        if not primary.voice and secondary.voice:
            primary.voice = secondary.voice

        # Remove secondary
        sec_norm = normalize_character_name(secondary.name)
        self._chars.pop(sec_norm, None)

    # --------------------------------------------------------
    # List / Export
    # --------------------------------------------------------

    def list_characters(self) -> List[Character]:
        return list(self._chars.values())

    def to_json(self) -> List[Dict]:
        return [c.to_dict() for c in self._chars.values()]
