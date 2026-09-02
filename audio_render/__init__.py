"""Audio rendering pipeline module."""

from .audio_utils import VoiceResolution, build_normalized_voice_lookup, resolve_voice_for_segment
from .silence_trim import trim_silence
from .tts_client import TTSClient
from .tts_engine_local import TTSEngine as LocalTTSEngine
from .tts_pipeline import TTSPipeline
from .tts_service import TTSEngine, TTSEngineContract
from .voice_router import VoiceRouter

__all__ = [
    "LocalTTSEngine",
    "TTSClient",
    "TTSEngine",
    "TTSEngineContract",
    "TTSPipeline",
    "VoiceResolution",
    "VoiceRouter",
    "build_normalized_voice_lookup",
    "resolve_voice_for_segment",
    "trim_silence",
]
