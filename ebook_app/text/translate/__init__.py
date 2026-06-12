# ebook_app/text/translate/__init__.py
from .translator import Translator
from .translation_profiles import TranslationProfile, get_profile, BUILTIN_PROFILES

__all__ = ["Translator", "TranslationProfile", "get_profile", "BUILTIN_PROFILES"]
