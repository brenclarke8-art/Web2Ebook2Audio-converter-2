# ebook_app/tts/emotion_voice_map.py
"""Mapping from emotion labels to voice style modifiers."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class VoiceModifier:
    """TTS speaking parameters adjusted for a given emotion."""
    speed_multiplier: float = 1.0
    pitch_shift: float = 0.0
    volume_db: float = 0.0
    voice_override: Optional[str] = None
    description: str = ""


# Default emotion → voice modifier mappings
EMOTION_VOICE_MAP: Dict[str, VoiceModifier] = {
    "neutral":    VoiceModifier(speed_multiplier=1.0),
    "happy":      VoiceModifier(speed_multiplier=1.1,  pitch_shift=1.0,  description="upbeat"),
    "sad":        VoiceModifier(speed_multiplier=0.9,  pitch_shift=-1.0, description="somber"),
    "angry":      VoiceModifier(speed_multiplier=1.15, pitch_shift=1.5,  volume_db=2.0, description="forceful"),
    "fearful":    VoiceModifier(speed_multiplier=1.2,  description="tense"),
    "surprised":  VoiceModifier(speed_multiplier=1.1,  pitch_shift=2.0),
    "disgusted":  VoiceModifier(speed_multiplier=0.95, pitch_shift=-0.5),
    "whispering": VoiceModifier(speed_multiplier=0.85, volume_db=-3.0,  description="hushed"),
}


def get_modifier(emotion: str) -> VoiceModifier:
    """Get voice modifier for *emotion*. Falls back to neutral."""
    return EMOTION_VOICE_MAP.get(emotion.lower(), EMOTION_VOICE_MAP["neutral"])


def apply_modifier(base_speed: float, emotion: str) -> float:
    """Return adjusted speaking speed for *emotion*."""
    return base_speed * get_modifier(emotion).speed_multiplier
