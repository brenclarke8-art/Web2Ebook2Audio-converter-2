# ebook_app/text/identify/pronouns.py
"""
ebook_app.models.pronouns

Context-aware pronoun analysis for translation.
Builds character profiles, tracks pronoun usage, and generates
pronoun correction rules for consistent translation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from collections import defaultdict

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Character Profile
# ----------------------------------------------------------------------

@dataclass
class CharacterProfile:
    """Tracks pronoun usage and inferred gender for a character."""
    name: str
    aliases: Set[str] = field(default_factory=set)
    detected_pronouns: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    gender: Optional[str] = None
    mention_count: int = 0
    contexts: List[str] = field(default_factory=list)

    def add_pronoun_usage(self, pronoun: str):
        self.detected_pronouns[pronoun.lower()] += 1

    def infer_gender(self) -> Optional[str]:
        """Infer gender from pronoun usage patterns."""
        if not self.detected_pronouns:
            return None

        male = {"he", "him", "his", "himself"}
        female = {"she", "her", "hers", "herself"}
        neutral = {"they", "them", "their", "theirs", "themselves"}

        male_count = sum(self.detected_pronouns.get(p, 0) for p in male)
        female_count = sum(self.detected_pronouns.get(p, 0) for p in female)
        neutral_count = sum(self.detected_pronouns.get(p, 0) for p in neutral)

        if male_count > female_count and male_count > neutral_count:
            self.gender = "male"
        elif female_count > male_count and female_count > neutral_count:
            self.gender = "female"
        elif neutral_count > 0:
            self.gender = "neutral"
        else:
            self.gender = None

        return self.gender

    def get_preferred_pronouns(self) -> Dict[str, str]:
        """Return the preferred pronoun set for this character."""
        if not self.gender:
            self.infer_gender()

        if self.gender == "male":
            return {
                "subject": "he",
                "object": "him",
                "possessive": "his",
                "possessive_pronoun": "his",
                "reflexive": "himself",
            }
        if self.gender == "female":
            return {
                "subject": "she",
                "object": "her",
                "possessive": "her",
                "possessive_pronoun": "hers",
                "reflexive": "herself",
            }
        if self.gender == "neutral":
            return {
                "subject": "they",
                "object": "them",
                "possessive": "their",
                "possessive_pronoun": "theirs",
                "reflexive": "themselves",
            }

        return {}


# ----------------------------------------------------------------------
# Pronoun Analyzer
# ----------------------------------------------------------------------

class PronounAnalyzer:
    """Extracts characters and links pronouns to them using context."""

    PRONOUNS = {
        "subject": ["he", "she", "they", "it"],
        "object": ["him", "her", "them", "it"],
        "possessive": ["his", "her", "their", "its"],
        "possessive_pronoun": ["his", "hers", "theirs"],
        "reflexive": ["himself", "herself", "themselves", "itself"],
    }

    NAME_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")

    HONORIFICS = {
        "mr", "mrs", "ms", "miss", "dr", "prof", "professor", "captain",
        "lord", "lady", "sir", "dame", "duke", "duchess", "earl", "count",
        "countess", "baron", "baroness", "general", "colonel", "major",
        "sergeant", "officer", "detective", "inspector", "agent",
        "king", "queen", "prince", "princess", "emperor", "empress",
    }

    _HONORIFIC_NAME_RE = re.compile(
        r"\b(?:"
        + "|".join(
            "".join(
                f"[{c.upper()}{c.lower()}]" if c.isalpha() else re.escape(c)
                for c in h
            )
            for h in sorted(HONORIFICS, key=len, reverse=True)
        )
        + r")\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b"
    )

    COMMON_WORDS = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
        "have", "has", "had", "do", "does", "did", "will", "would", "should",
        "could", "may", "might", "must", "can", "shall", "i", "you", "we",
        "chapter", "part", "section", "volume", "book", "page",
    }

    NON_CHARACTER_TOKENS = {
        "he", "she", "they", "it", "this", "that", "these", "those",
        "if", "when", "while", "since", "because", "however", "therefore",
        "yes", "no", "not", "mom", "dad", "mother", "father",
    }

    LOCATION_PREPOSITIONS = {"in", "at", "to", "from"}
    TITLE_ROLE_WORDS = {"adventurer", "rank", "knight", "saint", "guild"}

    def __init__(self):
        self.characters: Dict[str, CharacterProfile] = {}
        self.sentence_window = 3

    # ------------------------------------------------------------------
    # Character Extraction
    # ------------------------------------------------------------------

    def extract_characters_from_text(self, text: str) -> List[str]:
        sentences = self._split_sentences(text)
        potential = set()

        # Honorific-based extraction
        for match in self._HONORIFIC_NAME_RE.finditer(text):
            potential.add(match.group(1))

        # Capitalized-word extraction
        for sentence in sentences:
            for match in self.NAME_PATTERN.findall(sentence):
                if match in potential:
                    continue
                if not self._is_likely_character_name(match, sentence):
                    continue
                if match.lower() not in self.COMMON_WORDS:
                    potential.add(match)

        return sorted(potential, key=lambda x: text.count(x), reverse=True)

    def _is_likely_character_name(self, candidate: str, sentence: str) -> bool:
        if not candidate or len(candidate) <= 1:
            return False

        parts = candidate.split()
        if all(p.lower() in self.NON_CHARACTER_TOKENS for p in parts):
            return False

        if candidate.lower() in self.NON_CHARACTER_TOKENS:
            return False

        tokens = [
            re.sub(r"[^\w]", "", t).lower()
            for t in sentence.split()
        ]
        cand = candidate.lower()

        for i, token in enumerate(tokens):
            if token != cand:
                continue
            if i > 0 and tokens[i - 1] in self.LOCATION_PREPOSITIONS:
                return False
            if i + 1 < len(tokens) and tokens[i + 1] in self.TITLE_ROLE_WORDS:
                return False

        return True

    # ------------------------------------------------------------------
    # Main Analysis
    # ------------------------------------------------------------------

    def analyze_text(self, text: str, known_characters: Optional[List[str]] = None):
        sentences = self._split_sentences(text)

        # Initialize known characters
        if known_characters:
            for name in known_characters:
                if name not in self.characters:
                    self.characters[name] = CharacterProfile(name=name)

        # Extract characters if none provided
        if not known_characters:
            extracted = self.extract_characters_from_text(text)
            for name in extracted[:20]:
                if name not in self.characters:
                    self.characters[name] = CharacterProfile(name=name)

        # Analyze each sentence
        for idx, sentence in enumerate(sentences):
            self._analyze_sentence(sentence, sentences, idx)

        # Infer gender
        for character in self.characters.values():
            character.infer_gender()

    def _split_sentences(self, text: str) -> List[str]:
        parts = re.split(r"[.!?]+", text)
        return [p.strip() for p in parts if p.strip()]

    def _analyze_sentence(self, sentence: str, all_sentences: List[str], idx: int):
        mentioned = []
        for name, profile in self.characters.items():
            if name in sentence:
                mentioned.append(profile)
                profile.mention_count += 1
                if len(profile.contexts) < 5:
                    profile.contexts.append(sentence[:100])

        pronouns = []
        for word in sentence.lower().split():
            clean = re.sub(r"[^\w]", "", word)
            for ptype, plist in self.PRONOUNS.items():
                if clean in plist:
                    pronouns.append((clean, ptype))

        if pronouns and mentioned:
            for profile in mentioned:
                for pronoun, _ in pronouns:
                    profile.add_pronoun_usage(pronoun)

        elif pronouns:
            start = max(0, idx - self.sentence_window)
            recent = None
            for prev in reversed(all_sentences[start:idx]):
                for name, profile in self.characters.items():
                    if name in prev:
                        recent = profile
                        break
                if recent:
                    break

            if recent:
                for pronoun, _ in pronouns:
                    recent.add_pronoun_usage(pronoun)

    # ------------------------------------------------------------------
    # Rule Generation
    # ------------------------------------------------------------------

    def get_character_pronoun_mapping(self) -> Dict[str, Dict[str, str]]:
        mapping = {}
        for name, profile in self.characters.items():
            preferred = profile.get_preferred_pronouns()
            if preferred:
                mapping[name] = preferred
        return mapping

    def get_pronoun_correction_rules(
        self, target_mapping: Optional[Dict[str, str]] = None
    ) -> List[Dict]:
        rules = []

        for name, profile in self.characters.items():
            detected = profile.gender

            if target_mapping and name in target_mapping:
                desired = target_mapping[name]
                if desired != detected:
                    current = CharacterProfile(name=name)
                    current.gender = detected
                    current_pronouns = current.get_preferred_pronouns()

                    target = CharacterProfile(name=name)
                    target.gender = desired
                    target_pronouns = target.get_preferred_pronouns()

                    for ptype in ["subject", "object", "possessive", "reflexive"]:
                        if ptype in current_pronouns and ptype in target_pronouns:
                            c = current_pronouns[ptype]
                            t = target_pronouns[ptype]
                            if c != t:
                                rules.append(
                                    {
                                        "pattern": fr"\b{c}\b",
                                        "replacement": t,
                                        "is_regex": True,
                                        "case_sensitive": False,
                                        "description": f"{name}: {c} → {t}",
                                    }
                                )

        return rules

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def generate_report(self) -> str:
        lines = ["Character-Pronoun Analysis Report", "=" * 50, ""]

        for name, profile in sorted(
            self.characters.items(),
            key=lambda x: x[1].mention_count,
            reverse=True,
        ):
            lines.append(f"Character: {name}")
            lines.append(f"  Mentions: {profile.mention_count}")
            lines.append(f"  Gender: {profile.gender or 'Unknown'}")

            if profile.detected_pronouns:
                lines.append("  Pronoun Usage:")
                for pronoun, count in sorted(
                    profile.detected_pronouns.items(),
                    key=lambda x: x[1],
                    reverse=True,
                ):
                    lines.append(f"    {pronoun}: {count}")

            preferred = profile.get_preferred_pronouns()
            if preferred:
                lines.append(
                    f"  Preferred Pronouns: {', '.join(preferred.values())}"
                )

            if profile.contexts:
                lines.append(f"  Example: {profile.contexts[0][:80]}...")

            lines.append("")

        return "\n".join(lines)