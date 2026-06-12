# ebook_app/text/emotion/emotion_profiles.py
"""Pre-defined emotion profiles and intensity mappings."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class EmotionProfile:
    name: str
    keywords: List[str] = field(default_factory=list)
    tts_speaking_rate: float = 1.0
    tts_pitch_shift: float = 0.0
    voice_style: str = ""
    description: str = ""


BUILTIN_EMOTIONS: Dict[str, EmotionProfile] = {
    "neutral": EmotionProfile("neutral", tts_speaking_rate=1.0),
    "happy": EmotionProfile(
        "happy",
        keywords=["laughed", "smiled", "joy", "excited", "delighted"],
        tts_speaking_rate=1.1,
        tts_pitch_shift=1.0,
        voice_style="cheerful",
    ),
    "sad": EmotionProfile(
        "sad",
        keywords=["cried", "wept", "tears", "grief", "mourned"],
        tts_speaking_rate=0.9,
        tts_pitch_shift=-1.0,
        voice_style="sad",
    ),
    "angry": EmotionProfile(
        "angry",
        keywords=["shouted", "yelled", "furious", "rage", "snapped"],
        tts_speaking_rate=1.15,
        tts_pitch_shift=1.5,
        voice_style="angry",
    ),
    "fearful": EmotionProfile(
        "fearful",
        keywords=["trembled", "shivered", "terrified", "afraid", "scared"],
        tts_speaking_rate=1.2,
        voice_style="fearful",
    ),
    "surprised": EmotionProfile(
        "surprised",
        keywords=["gasped", "startled", "shocked", "astonished"],
        tts_speaking_rate=1.1,
        tts_pitch_shift=2.0,
    ),
    "disgusted": EmotionProfile(
        "disgusted",
        keywords=["sneered", "revolted", "disgusting", "repulsed"],
        tts_speaking_rate=0.95,
        tts_pitch_shift=-0.5,
    ),
    "whispering": EmotionProfile(
        "whispering",
        keywords=["whispered", "murmured", "breathed"],
        tts_speaking_rate=0.85,
        voice_style="whispering",
    ),
}
