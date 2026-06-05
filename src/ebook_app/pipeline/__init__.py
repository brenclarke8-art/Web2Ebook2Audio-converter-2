"""
ebook_app.pipeline
------------------

Unified pipeline package for the 7‑phase hybrid novel‑processing system.

This package exposes:
    - PipelineController (main orchestrator)
    - PipelineSettings (configuration container)
    - PIPELINE_STEPS (canonical step list)
    - Core pipeline modules (Pass‑1, Pass‑2, rebuild, voices, characters)
"""

from .pipeline_controller import PipelineController, PipelineSettings
from .pipeline_steps import PIPELINE_STEPS

# Core pipeline modules
from .pass1_extractor import Pass1Extractor
from .pass2_classifier import Pass2Classifier, LLMClient
from .character_merger import CharacterMerger
from .chapter_rebuilder import ChapterRebuilder

# VoiceRouter lives in ebook_app.tts
try:
    from ebook_app.tts.voice_router import VoiceRouter
except Exception:
    VoiceRouter = None

__all__ = [
    "PipelineController",
    "PipelineSettings",
    "PIPELINE_STEPS",
    "Pass1Extractor",
    "Pass2Classifier",
    "LLMClient",
    "CharacterMerger",
    "VoiceRouter",
    "ChapterRebuilder",
]
