"""LLM processing, segmentation, and translation pipeline module."""

from .character_db_updater import CharacterMerger
from .dialogue_detector import DialogueDetector
from .llm_client import LLMClient
from .pronouns import PronounResolver
from .role_tagger import Pass1Extractor
from .segment_models import DetectedCharacter, Segment, SegmentationResult
from .segmenter import DialogueSegmentationService
from .speaker_llm import DialogueParser, OllamaChatClient, ParseResult
from .structured_output import (
    CharacterRegistry,
    LLMResultInput,
    LLMSegmentInput,
    normalize_segments,
    parse_structured_llm_response,
    sanitize_json_text,
)
from .translation_profiles import BUILTIN_PROFILES, TranslationProfile, get_profile
from .translator import Translator
from .type_classifier import Pass2Classifier

__all__ = [
    "BUILTIN_PROFILES",
    "CharacterMerger",
    "CharacterRegistry",
    "DetectedCharacter",
    "DialogueDetector",
    "DialogueParser",
    "DialogueSegmentationService",
    "LLMClient",
    "LLMResultInput",
    "LLMSegmentInput",
    "OllamaChatClient",
    "ParseResult",
    "Pass1Extractor",
    "Pass2Classifier",
    "PronounResolver",
    "Segment",
    "SegmentationResult",
    "TranslationProfile",
    "Translator",
    "get_profile",
    "normalize_segments",
    "parse_structured_llm_response",
    "sanitize_json_text",
]
