# ebook_app/text/emotion/emotion_tagger.py
"""Emotion tagger — annotates segments with emotion labels."""
from __future__ import annotations
import logging
import re
from typing import Any, Dict, List, Optional

from .emotion_profiles import BUILTIN_EMOTIONS, EmotionProfile
from .emotion_llm import EmotionLlm

logger = logging.getLogger(__name__)


class EmotionTagger:
    """
    Tag text segments with emotion labels using keyword heuristics first,
    then optional LLM fallback for unclassified segments.
    """

    def __init__(
        self,
        use_llm: bool = False,
        llm_url: str = "http://127.0.0.1:11434/api/generate",
        llm_model: str = "qwen2.5-coder:7b",
        profiles: Optional[Dict[str, EmotionProfile]] = None,
    ):
        self.use_llm = use_llm
        self.profiles = profiles or BUILTIN_EMOTIONS
        self._llm: Optional[EmotionLlm] = None
        if use_llm:
            self._llm = EmotionLlm(llm_url=llm_url, model=llm_model)

    def tag_segment(self, segment: Dict[str, Any]) -> Dict[str, Any]:
        """Add an "emotion" key to *segment* dict. Returns the updated dict."""
        text = segment.get("text", "").lower()
        emotion = self._keyword_match(text)
        if not emotion and self._llm:
            results = self._llm.classify_batch([segment.get("text", "")])
            emotion = results[0] if results else "neutral"
        segment["emotion"] = emotion or "neutral"
        return segment

    def tag_all(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Tag all segments. Uses batch LLM call when enabled."""
        if self.use_llm and self._llm:
            untagged_idx = []
            for i, seg in enumerate(segments):
                emotion = self._keyword_match(seg.get("text", "").lower())
                if emotion:
                    seg["emotion"] = emotion
                else:
                    seg["emotion"] = "neutral"
                    untagged_idx.append(i)
            if untagged_idx:
                texts = [segments[i].get("text", "") for i in untagged_idx]
                labels = self._llm.classify_batch(texts)
                for i, label in zip(untagged_idx, labels):
                    segments[i]["emotion"] = label
            return segments
        return [self.tag_segment(s) for s in segments]

    def _keyword_match(self, text: str) -> str:
        for name, profile in self.profiles.items():
            if name == "neutral":
                continue
            for kw in profile.keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", text):
                    return name
        return ""
