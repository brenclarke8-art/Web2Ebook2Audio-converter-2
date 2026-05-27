#!/usr/bin/env python3
"""
Context-Aware Pronoun Analysis for Translation

This module provides intelligent pronoun tracking and character-pronoun linking
to ensure consistent and accurate pronoun translation based on context.
"""

import re
import logging
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class CharacterProfile:
    """Profile tracking a character's mentions and associated pronouns"""
    name: str
    aliases: Set[str] = field(default_factory=set)  # Alternative names/spellings
    detected_pronouns: Dict[str, int] = field(default_factory=lambda: defaultdict(int))  # pronoun -> count
    gender: Optional[str] = None  # 'male', 'female', 'neutral', or None
    mention_count: int = 0
    contexts: List[str] = field(default_factory=list)  # Sample sentences mentioning character

    def add_pronoun_usage(self, pronoun: str):
        """Track pronoun usage for this character"""
        self.detected_pronouns[pronoun.lower()] += 1

    def infer_gender(self):
        """Infer gender from pronoun usage patterns"""
        if not self.detected_pronouns:
            return None

        male_pronouns = {'he', 'him', 'his', 'himself'}
        female_pronouns = {'she', 'her', 'hers', 'herself'}
        neutral_pronouns = {'they', 'them', 'their', 'theirs', 'themselves'}

        male_count = sum(self.detected_pronouns.get(p, 0) for p in male_pronouns)
        female_count = sum(self.detected_pronouns.get(p, 0) for p in female_pronouns)
        neutral_count = sum(self.detected_pronouns.get(p, 0) for p in neutral_pronouns)

        # Determine dominant gender
        if male_count > female_count and male_count > neutral_count:
            self.gender = 'male'
        elif female_count > male_count and female_count > neutral_count:
            self.gender = 'female'
        elif neutral_count > 0:
            self.gender = 'neutral'
        else:
            self.gender = None

        return self.gender

    def get_preferred_pronouns(self) -> Dict[str, str]:
        """Get the most commonly used pronouns for this character"""
        if not self.gender:
            self.infer_gender()

        if self.gender == 'male':
            return {
                'subject': 'he',
                'object': 'him',
                'possessive': 'his',
                'possessive_pronoun': 'his',
                'reflexive': 'himself'
            }
        elif self.gender == 'female':
            return {
                'subject': 'she',
                'object': 'her',
                'possessive': 'her',
                'possessive_pronoun': 'hers',
                'reflexive': 'herself'
            }
        elif self.gender == 'neutral':
            return {
                'subject': 'they',
                'object': 'them',
                'possessive': 'their',
                'possessive_pronoun': 'theirs',
                'reflexive': 'themselves'
            }
        else:
            return {}


class PronounAnalyzer:
    """Analyzes text to link pronouns with characters using context"""

    # Pronouns to track
    PRONOUNS = {
        'subject': ['he', 'she', 'they', 'it'],
        'object': ['him', 'her', 'them', 'it'],
        'possessive': ['his', 'her', 'their', 'its'],
        'possessive_pronoun': ['his', 'hers', 'theirs'],
        'reflexive': ['himself', 'herself', 'themselves', 'itself']
    }

    # Patterns to identify potential character names (capitalized words)
    NAME_PATTERN = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b')

    # Honorific titles that reliably precede character names (name-pattern filter).
    HONORIFICS = {
        'mr', 'mrs', 'ms', 'miss', 'dr', 'prof', 'professor', 'captain', 'cap',
        'lord', 'lady', 'sir', 'dame', 'duke', 'duchess', 'earl', 'count',
        'countess', 'baron', 'baroness', 'general', 'colonel', 'major',
        'sergeant', 'officer', 'detective', 'inspector', 'agent',
        'king', 'queen', 'prince', 'princess', 'emperor', 'empress',
    }

    # Pre-compiled pattern for honorific-preceded names (sorted longest-first so
    # longer titles like "professor" match before the shorter "prof").
    # Built without re.IGNORECASE: each honorific letter is wrapped in a
    # [Xx] character class so both "Mr" and "mr" are matched, while the
    # captured name group remains a strict [A-Z][a-z]+ match so that
    # ordinary words like "gave" are never captured.
    _HONORIFIC_NAME_RE = re.compile(
        r'\b(?:' +
        '|'.join(
            ''.join(
                f'[{c.upper()}{c.lower()}]' if c.isalpha() else re.escape(c)
                for c in h
            )
            for h in sorted(HONORIFICS, key=len, reverse=True)
        ) +
        r')\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
    )

    # Common words that are not character names
    COMMON_WORDS = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should',
        'could', 'may', 'might', 'must', 'can', 'shall', 'i', 'you', 'we',
        'chapter', 'part', 'section', 'volume', 'book', 'page', 'monday',
        'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
        'january', 'february', 'march', 'april', 'may', 'june', 'july',
        'august', 'september', 'october', 'november', 'december'
    }

    # Additional tokens frequently capitalized in prose but not character names.
    NON_CHARACTER_TOKENS = {
        'he', 'she', 'they', 'it', 'this', 'that', 'these', 'those',
        'if', 'when', 'while', 'since', 'because', 'however', 'therefore',
        'yes', 'no', 'not', 'thump', 'clack', 'bang',
        'mom', 'dad', 'mother', 'father',
    }
    LOCATION_PREPOSITIONS = {'in', 'at', 'to', 'from'}
    TITLE_ROLE_WORDS = {'adventurer', 'rank', 'knight', 'saint', 'guild'}

    def __init__(self):
        logger.debug("Initializing PronounAnalyzer")
        self.characters: Dict[str, CharacterProfile] = {}
        self.sentence_window = 3  # Look back/forward N sentences for context
        logger.debug(f"Sentence window set to {self.sentence_window}")

    def extract_characters_from_text(self, text: str) -> List[str]:
        """Extract potential character names from text"""
        sentences = self._split_sentences(text)
        potential_names: set = set()

        # First pass: names preceded by honorific titles are high-confidence
        # (POS-style filter — honorifics reliably precede proper nouns/names).
        honorific_names: set = set()
        for match in self._HONORIFIC_NAME_RE.finditer(text):
            name = match.group(1)
            honorific_names.add(name)
            logger.debug("Honorific-preceded name found: '%s'", name)
        if honorific_names:
            logger.debug(
                "Honorific-based extraction: %d name(s): %s",
                len(honorific_names), sorted(honorific_names),
            )
        potential_names.update(honorific_names)

        # Second pass: general capitalized-word extraction with heuristic filters.
        for sentence in sentences:
            # Find capitalized words that might be names
            matches = self.NAME_PATTERN.findall(sentence)
            for match in matches:
                if match in honorific_names:
                    # Already captured via the honorific pass; skip filter.
                    continue
                if not self._is_likely_character_name(match, sentence):
                    continue
                # Filter out common words.
                if match.lower() not in self.COMMON_WORDS:
                    potential_names.add(match)

        result = sorted(potential_names, key=lambda x: text.count(x), reverse=True)
        logger.debug(
            "Extracted %d potential character name(s): %s",
            len(result), result[:15],
        )
        return result

    def _is_likely_character_name(self, candidate: str, sentence: str) -> bool:
        """Return True when candidate resembles a plausible character name."""
        if not candidate or len(candidate) <= 1:
            return False

        token_parts = candidate.strip().split()
        if not token_parts:
            return False

        # Reject candidates composed entirely of filtered non-name tokens.
        if all(token.lower() in self.NON_CHARACTER_TOKENS for token in token_parts):
            return False

        # Reject obvious sentence-starter/connector tokens captured by capitalization.
        if candidate.lower() in self.NON_CHARACTER_TOKENS:
            return False

        candidate_lower = candidate.lower()
        sentence_tokens = [re.sub(r'[^\w]', '', token).lower() for token in sentence.split()]
        for idx, token in enumerate(sentence_tokens):
            if token != candidate_lower:
                continue
            if idx > 0 and sentence_tokens[idx - 1] in self.LOCATION_PREPOSITIONS:
                return False
            if idx + 1 < len(sentence_tokens) and sentence_tokens[idx + 1] in self.TITLE_ROLE_WORDS:
                return False

        return True

    def analyze_text(self, text: str, known_characters: Optional[List[str]] = None):
        """Analyze text to build character-pronoun relationships"""
        logger.debug(f"analyze_text called: text_length={len(text)}, known_characters={known_characters}")
        sentences = self._split_sentences(text)
        logger.debug(f"Text split into {len(sentences)} sentences")

        # Initialize known characters
        if known_characters:
            logger.debug(f"Initializing {len(known_characters)} known characters")
            for char in known_characters:
                if char not in self.characters:
                    self.characters[char] = CharacterProfile(name=char)
            logger.debug(f"Known characters initialized: {list(self.characters.keys())}")

        # Extract characters from text if not provided
        if not known_characters:
            logger.debug("No known characters provided, extracting from text")
            extracted = self.extract_characters_from_text(text)
            logger.debug(f"Extracted {len(extracted)} potential character names")
            for char in extracted[:20]:  # Limit to top 20 to avoid noise
                if char not in self.characters:
                    self.characters[char] = CharacterProfile(name=char)
            logger.debug(f"Characters initialized from extraction: {list(self.characters.keys())[:20]}")

        # Analyze each sentence for character-pronoun relationships
        logger.debug("Starting sentence analysis loop")
        for i, sentence in enumerate(sentences):
            if i % 100 == 0:
                logger.debug(f"Analyzing sentence {i+1}/{len(sentences)}")
            self._analyze_sentence(sentence, sentences, i)

        # Infer gender for all characters
        logger.debug("Inferring gender for all characters")
        for character in self.characters.values():
            character.infer_gender()

        logger.info(f"Analyzed {len(sentences)} sentences, found {len(self.characters)} characters")
        logger.debug(f"Character analysis complete")

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        # Simple sentence splitting
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _analyze_sentence(self, sentence: str, all_sentences: List[str], sentence_idx: int):
        """Analyze a single sentence for character-pronoun links"""
        # Find all characters mentioned in this sentence
        mentioned_characters = []
        for char_name, character in self.characters.items():
            if char_name in sentence:
                mentioned_characters.append(character)
                character.mention_count += 1
                if len(character.contexts) < 5:  # Store up to 5 example contexts
                    character.contexts.append(sentence[:100])

        # Find all pronouns in this sentence
        pronouns_in_sentence = []
        words = sentence.lower().split()
        for word in words:
            word_clean = re.sub(r'[^\w]', '', word)  # Remove punctuation
            for pronoun_type, pronoun_list in self.PRONOUNS.items():
                if word_clean in pronoun_list:
                    pronouns_in_sentence.append((word_clean, pronoun_type))

        # Link pronouns to characters using context
        if pronouns_in_sentence and mentioned_characters:
            # Simple heuristic: if character is mentioned in same sentence, link pronouns
            for character in mentioned_characters:
                for pronoun, pronoun_type in pronouns_in_sentence:
                    character.add_pronoun_usage(pronoun)

        # Check previous sentences for context (coreference resolution)
        elif pronouns_in_sentence and not mentioned_characters:
            # Look back at previous sentences for character mentions
            context_start = max(0, sentence_idx - self.sentence_window)
            context_sentences = all_sentences[context_start:sentence_idx]

            # Find the most recently mentioned character
            recent_character = None
            for prev_sentence in reversed(context_sentences):
                for char_name, character in self.characters.items():
                    if char_name in prev_sentence:
                        recent_character = character
                        break
                if recent_character:
                    break

            # Link pronouns to recent character
            if recent_character:
                for pronoun, pronoun_type in pronouns_in_sentence:
                    recent_character.add_pronoun_usage(pronoun)

    def get_character_pronoun_mapping(self) -> Dict[str, Dict[str, str]]:
        """Get mapping of characters to their preferred pronouns"""
        mapping = {}
        for char_name, character in self.characters.items():
            preferred = character.get_preferred_pronouns()
            if preferred:
                mapping[char_name] = preferred
        return mapping

    def get_pronoun_correction_rules(self, target_mapping: Optional[Dict[str, str]] = None) -> List[Dict]:
        """Generate pronoun correction rules based on analysis

        Args:
            target_mapping: Optional dict mapping character names to desired gender
                          e.g., {'Alice': 'female', 'Bob': 'male'}
        """
        rules = []

        for char_name, character in self.characters.items():
            # Get detected gender
            detected_gender = character.gender

            # Check if we need to override
            if target_mapping and char_name in target_mapping:
                desired_gender = target_mapping[char_name]
                if desired_gender != detected_gender:
                    # Generate correction rules
                    logger.info(f"Generating pronoun corrections for {char_name}: {detected_gender} -> {desired_gender}")

                    # Get current and desired pronouns
                    current_profile = CharacterProfile(name=char_name)
                    current_profile.gender = detected_gender
                    current_pronouns = current_profile.get_preferred_pronouns()

                    target_profile = CharacterProfile(name=char_name)
                    target_profile.gender = desired_gender
                    target_pronouns = target_profile.get_preferred_pronouns()

                    # Create rules for each pronoun type
                    for pronoun_type in ['subject', 'object', 'possessive', 'reflexive']:
                        if pronoun_type in current_pronouns and pronoun_type in target_pronouns:
                            current = current_pronouns[pronoun_type]
                            target = target_pronouns[pronoun_type]

                            if current != target:
                                rules.append({
                                    'pattern': f'\\b{current}\\b',
                                    'replacement': target,
                                    'is_regex': True,
                                    'case_sensitive': False,
                                    'description': f'Correct {char_name} pronoun: {current} -> {target}'
                                })

        return rules

    def generate_report(self) -> str:
        """Generate a human-readable report of character-pronoun analysis"""
        report = ["Character-Pronoun Analysis Report", "=" * 50, ""]

        for char_name, character in sorted(self.characters.items(), key=lambda x: x[1].mention_count, reverse=True):
            report.append(f"Character: {char_name}")
            report.append(f"  Mentions: {character.mention_count}")
            report.append(f"  Detected Gender: {character.gender or 'Unknown'}")

            if character.detected_pronouns:
                report.append(f"  Pronoun Usage:")
                for pronoun, count in sorted(character.detected_pronouns.items(), key=lambda x: x[1], reverse=True):
                    report.append(f"    {pronoun}: {count}")

            preferred = character.get_preferred_pronouns()
            if preferred:
                report.append(f"  Preferred Pronouns: {', '.join(preferred.values())}")

            if character.contexts:
                report.append(f"  Example Context: {character.contexts[0][:80]}...")

            report.append("")

        return "\n".join(report)


# Example usage
if __name__ == '__main__':
    # Example text
    sample_text = """
    Alice walked into the room. She was tired from the long journey.
    Bob greeted her warmly. He had been waiting for hours.
    Alice smiled at him. She appreciated his patience.
    They sat down and began to talk. Alice told him about her adventure.
    Bob listened intently. He was fascinated by her stories.
    """

    analyzer = PronounAnalyzer()
    analyzer.analyze_text(sample_text, known_characters=['Alice', 'Bob'])

    print(analyzer.generate_report())

    # Get pronoun mapping
    mapping = analyzer.get_character_pronoun_mapping()
    print("\nCharacter Pronoun Mapping:")
    for char, pronouns in mapping.items():
        print(f"  {char}: {pronouns}")

    # Example: Correct Alice's pronouns to male
    correction_rules = analyzer.get_pronoun_correction_rules({'Alice': 'male'})
    print("\nGenerated Correction Rules:")
    for rule in correction_rules:
        print(f"  {rule['pattern']} -> {rule['replacement']}")
