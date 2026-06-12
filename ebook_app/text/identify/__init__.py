# ebook_app/text/identify/__init__.py
from .role_tagger import Pass1Extractor
from .speaker_llm import OllamaChatClient
from .type_classifier import Pass2Classifier
from .character_db_updater import CharacterMerger

__all__ = [
    "Pass1Extractor",
    "OllamaChatClient",
    "Pass2Classifier",
    "CharacterMerger",
]
