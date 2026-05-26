"""
ebook_app.models.translation

AI-powered translation engine with:
- language detection
- custom translation rules
- pronoun analysis (optional)
- chapter-by-chapter translation pipeline
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ebook_app.models.pronouns import PronounAnalyzer, CharacterProfile

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Translation Rule Data Classes
# ----------------------------------------------------------------------

@dataclass
class TranslationRule:
    """Custom translation rule applied after AI translation."""
    pattern: str
    replacement: str
    is_regex: bool = False
    case_sensitive: bool = True


@dataclass
class TranslationConfig:
    """Configuration for the Translator."""
    enabled: bool = False
    source_language: str = "auto"
    target_language: str = "en"

    # AI translation API
    api_url: str = "http://localhost:5000/translate"
    api_key: Optional[str] = None

    # Custom rules
    custom_rules: List[TranslationRule] = field(default_factory=list)

    # Rule presets
    preserve_honorifics: bool = True
    preserve_names: bool = True

    # Pronoun analysis
    enable_pronoun_analysis: bool = True
    character_genders: Optional[Dict[str, str]] = None
    auto_detect_characters: bool = True


# ----------------------------------------------------------------------
# Language Detection
# ----------------------------------------------------------------------

class LanguageDetector:
    """Simple heuristic-based language detection."""

    LANGUAGE_PATTERNS = {
        "ja": ["の", "は", "を", "に", "で", "と", "が", "も", "から", "まで"],
        "zh": ["的", "了", "是", "在", "我", "有", "和", "人", "这", "中"],
        "ko": ["은", "는", "이", "가", "을", "를", "의", "에", "와", "과"],
        "ru": ["и", "в", "не", "на", "я", "что", "с", "он", "а", "как"],
        "es": ["de", "la", "que", "el", "en", "y", "a", "los", "se", "del"],
        "fr": ["de", "la", "le", "et", "des", "les", "du", "un", "une", "dans"],
        "de": ["der", "die", "und", "in", "den", "von", "zu", "das", "mit", "sich"],
    }

    @staticmethod
    def detect_language(text: str) -> str:
        if not text or len(text) < 50:
            return "unknown"

        # ASCII-only → likely English
        try:
            text.encode("ascii")
            return "en"
        except UnicodeEncodeError:
            pass

        text_lower = text.lower()
        scores = {}

        for lang, patterns in LanguageDetector.LANGUAGE_PATTERNS.items():
            score = sum(1 for p in patterns if p in text_lower)
            if score > 0:
                scores[lang] = score

        return max(scores, key=scores.get) if scores else "unknown"


# ----------------------------------------------------------------------
# Translator
# ----------------------------------------------------------------------

class Translator:
    """Main translation engine with optional pronoun analysis."""

    def __init__(self, config: TranslationConfig):
        self.config = config
        self.detector = LanguageDetector()
        self.pronoun_analyzer = (
            PronounAnalyzer() if config.enable_pronoun_analysis else None
        )

        logger.debug("Translator initialized with config: %s", config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def translate_text(self, text: str) -> str:
        """Translate a single block of text."""
        if not self.config.enabled:
            return text

        if not text.strip():
            return text

        # Auto-detect language
        source_lang = (
            self.detector.detect_language(text)
            if self.config.source_language == "auto"
            else self.config.source_language
        )

        if source_lang == self.config.target_language:
            return text

        if source_lang == "unknown":
            logger.warning("Language detection failed; skipping translation")
            return text

        try:
            translated = self._call_ai_translator(
                text, source_lang, self.config.target_language
            )
            translated = self._apply_custom_rules(translated)
            return translated
        except Exception as exc:
            logger.error("Translation failed: %s", exc)
            return text

    def translate_chapters(self, chapters: List[Dict]) -> List[Dict]:
        """Translate a list of chapters with optional pronoun analysis."""
        if not self.config.enabled:
            return chapters

        # Step 1: Pronoun analysis
        if self.pronoun_analyzer:
            self._analyze_pronouns_in_chapters(chapters)

        # Step 2: Translate each chapter
        translated = []
        for ch in chapters:
            translated.append(
                {
                    "url": ch["url"],
                    "title": self.translate_text(ch["title"]),
                    "content": self.translate_text(ch["content"]),
                }
            )

        # Step 3: Apply pronoun corrections
        if self.pronoun_analyzer:
            translated = self._apply_pronoun_corrections(translated)

        return translated

    # ------------------------------------------------------------------
    # Pronoun Analysis
    # ------------------------------------------------------------------

    def _analyze_pronouns_in_chapters(self, chapters: List[Dict]):
        combined = "\n\n".join(ch["content"] for ch in chapters)

        known = (
            list(self.config.character_genders.keys())
            if self.config.character_genders
            else None
        )

        self.pronoun_analyzer.analyze_text(combined, known_characters=known)

        # Generate correction rules
        if self.config.character_genders:
            rules = self.pronoun_analyzer.get_pronoun_correction_rules(
                self.config.character_genders
            )
            for rule in rules:
                self.add_rule(
                    pattern=rule["pattern"],
                    replacement=rule["replacement"],
                    is_regex=rule["is_regex"],
                    case_sensitive=rule.get("case_sensitive", True),
                )

    def _apply_pronoun_corrections(self, chapters: List[Dict]) -> List[Dict]:
        corrected = []
        for ch in chapters:
            corrected.append(
                {
                    "url": ch["url"],
                    "title": ch["title"],
                    "content": self._apply_custom_rules(ch["content"]),
                }
            )
        return corrected

    # ------------------------------------------------------------------
    # AI Translation
    # ------------------------------------------------------------------

    def _call_ai_translator(self, text: str, source: str, target: str) -> str:
        """Call the external AI translation API."""
        import requests

        payload = {"text": text, "source": source, "target": target}
        headers = {}

        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        response = requests.post(
            self.config.api_url, json=payload, headers=headers, timeout=300
        )
        response.raise_for_status()

        data = response.json()

        # Flexible response formats
        for key in ("translated_text", "translation", "text"):
            if key in data:
                return data[key]

        raise ValueError(f"Unexpected API response: {data}")

    # ------------------------------------------------------------------
    # Custom Rules
    # ------------------------------------------------------------------

    def _apply_custom_rules(self, text: str) -> str:
        if not self.config.custom_rules:
            return text

        result = text
        for rule in self.config.custom_rules:
            try:
                if rule.is_regex:
                    flags = 0 if rule.case_sensitive else re.IGNORECASE
                    result = re.sub(rule.pattern, rule.replacement, result, flags=flags)
                else:
                    if rule.case_sensitive:
                        result = result.replace(rule.pattern, rule.replacement)
                    else:
                        pattern = re.compile(re.escape(rule.pattern), re.IGNORECASE)
                        result = pattern.sub(rule.replacement, result)
            except Exception as exc:
                logger.warning(
                    "Failed to apply rule '%s' -> '%s': %s",
                    rule.pattern,
                    rule.replacement,
                    exc,
                )

        return result

    def add_rule(
        self,
        pattern: str,
        replacement: str,
        is_regex: bool = False,
        case_sensitive: bool = True,
    ):
        self.config.custom_rules.append(
            TranslationRule(
                pattern=pattern,
                replacement=replacement,
                is_regex=is_regex,
                case_sensitive=case_sensitive,
            )
        )

    def clear_rules(self):
        self.config.custom_rules.clear()


# ----------------------------------------------------------------------
# Rule Presets
# ----------------------------------------------------------------------

class TranslationRulePresets:
    """Factory for common translation rule presets."""

    @staticmethod
    def character_name_rule(original: str, translated: str) -> TranslationRule:
        return TranslationRule(
            pattern=fr"\b{re.escape(original)}\b",
            replacement=translated,
            is_regex=True,
            case_sensitive=True,
        )

    @staticmethod
    def pronoun_rule(source: str, target: str) -> TranslationRule:
        return TranslationRule(
            pattern=fr"\b{re.escape(source)}\b",
            replacement=target,
            is_regex=True,
            case_sensitive=False,
        )

    @staticmethod
    def honorific_preservation_rules() -> List[TranslationRule]:
        honorifics = ["-san", "-kun", "-chan", "-sama", "-senpai", "-sensei", "-dono"]
        return [
            TranslationRule(pattern=h, replacement=h, is_regex=False)
            for h in honorifics
        ]

    @staticmethod
    def term_consistency_rule(original: str, preferred: str) -> TranslationRule:
        return TranslationRule(
            pattern=fr"\b{re.escape(original)}\b",
            replacement=preferred,
            is_regex=True,
            case_sensitive=False,
        )


# ----------------------------------------------------------------------
# Factory
# ----------------------------------------------------------------------

def create_translator_from_dict(config_dict: dict) -> Translator:
    """Create a Translator instance from a raw config dictionary."""
    rules = []
    if "custom_rules" in config_dict:
        for rule_data in config_dict["custom_rules"]:
            rules.append(TranslationRule(**rule_data))

        config_dict = config_dict.copy()
        config_dict["custom_rules"] = rules

    return Translator(TranslationConfig(**config_dict))