# ebook_app/pipeline/__init__.py
"""
ebook_app.pipeline
------------------
Unified pipeline package.
"""
from .controller import PipelineController, PipelineSettings
from .phases import PIPELINE_STEPS
from .chapter_rebuilder import ChapterRebuilder

try:
    from ebook_app.tts.voice_router import VoiceRouter
except Exception:
    VoiceRouter = None

__all__ = [
    "PipelineController",
    "PipelineSettings",
    "PIPELINE_STEPS",
    "ChapterRebuilder",
    "VoiceRouter",
]
