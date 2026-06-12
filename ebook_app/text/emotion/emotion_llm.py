# ebook_app/text/emotion/emotion_llm.py
"""LLM-based emotion classification for text segments."""
from __future__ import annotations
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

EMOTION_SYSTEM_PROMPT = """You are an expert literary analyst. For each text segment provided, identify the dominant emotion.
Choose from: neutral, happy, sad, angry, fearful, surprised, disgusted, whispering.
Return a JSON array where each element has keys "index" and "emotion".
"""

EMOTION_LABELS = ["neutral", "happy", "sad", "angry", "fearful", "surprised", "disgusted", "whispering"]


class EmotionLlm:
    """Classify emotion for a batch of text segments using an LLM."""

    def __init__(
        self,
        llm_url: str = "http://127.0.0.1:11434/api/generate",
        model: str = "qwen2.5-coder:7b",
        timeout: int = 120,
    ):
        self.llm_url = llm_url
        self.model = model
        self.timeout = timeout

    def classify_batch(self, texts: List[str]) -> List[str]:
        """
        Classify emotion for each text in *texts*.
        Returns a list of emotion labels (one per input).
        Falls back to "neutral" on any error.
        """
        from ebook_app.text.identify.speaker_llm import OllamaChatClient
        client = OllamaChatClient(
            base_url=self.llm_url,
            model=self.model,
            timeout=self.timeout,
        )
        user = "\n".join(
            f"{i}: {t[:300]}" for i, t in enumerate(texts)
        )
        try:
            result = client.ask_json_any(
                system=EMOTION_SYSTEM_PROMPT,
                user=user,
                chapter_id="emotion_classification",
            )
            if isinstance(result, list):
                mapping = {item["index"]: item["emotion"] for item in result if "index" in item}
                return [mapping.get(i, "neutral") for i in range(len(texts))]
        except Exception as exc:
            logger.warning("Emotion LLM classification failed: %s", exc)
        return ["neutral"] * len(texts)
