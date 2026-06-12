# ebook_app/tts/__init__.py
from .tts_service import TTSEngine, TTSEngineContract
from .voice_router import VoiceRouter
from .audio_utils import resolve_voice_for_segment, VoiceResolution

__all__ = [
    "TTSEngine",
    "TTSEngineContract",
    "VoiceRouter",
    "resolve_voice_for_segment",
    "VoiceResolution",
]
