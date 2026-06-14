# ebook_app/tts/__init__.py
try:
    from .tts_service import TTSEngine, TTSEngineContract
    from .voice_router import VoiceRouter
    from .audio_utils import resolve_voice_for_segment, VoiceResolution
except ImportError:
    pass

__all__ = [
    "TTSEngine",
    "TTSEngineContract",
    "VoiceRouter",
    "resolve_voice_for_segment",
    "VoiceResolution",
]
