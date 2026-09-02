# ebook_app/text/translate/translation_profiles.py
"""Pre-defined translation profiles for common language pairs and genres."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class TranslationProfile:
    """Configuration for a specific translation task."""
    name: str
    source_language: str
    target_language: str
    provider: str = "llm"
    llm_model: str = "qwen2.5-coder:7b"
    preserve_honorifics: bool = False
    extra_glossary: Dict[str, str] = field(default_factory=dict)
    notes: str = ""


BUILTIN_PROFILES: Dict[str, TranslationProfile] = {
    "zh_en_webnovel": TranslationProfile(
        name="Chinese Web Novel → English",
        source_language="zh",
        target_language="en",
        preserve_honorifics=True,
        notes="Optimized for xianxia/wuxia genre with cultivation terminology.",
    ),
    "ko_en_webnovel": TranslationProfile(
        name="Korean Web Novel → English",
        source_language="ko",
        target_language="en",
        preserve_honorifics=True,
    ),
    "ja_en_lightnovel": TranslationProfile(
        name="Japanese Light Novel → English",
        source_language="ja",
        target_language="en",
        preserve_honorifics=True,
        notes="Preserves honorifics like -san, -kun, -chan.",
    ),
}


def get_profile(name: str) -> TranslationProfile:
    if name not in BUILTIN_PROFILES:
        raise KeyError(f"Unknown translation profile: {name!r}. Available: {list(BUILTIN_PROFILES)}")
    return BUILTIN_PROFILES[name]
