"""LLM-based emotion classification for text segments."""
from __future__ import annotations

import json
import logging
from typing import List, Optional

from ebook_app.text.identify.llm_client import LLMClient

logger = logging.getLogger(__name__)

EMOTION_SYSTEM_PROMPT = """You are an expert literary analyst. For each text segment provided, identify the dominant emotion.
Choose from: neutral, happy, sad, angry, fearful, surprised, disgusted, whispering.
Return a JSON array where each element has keys "index" and "emotion".
"""

EMOTION_LABELS = ["neutral", "happy", "sad", "angry", "fearful", "surprised", "disgusted", "whispering"]


class EmotionLlm:
    """Classify emotion for a batch of text segments using an LLM.

    This class is defensive: it tolerates different JSON shapes returned by the LLM,
    falls back to "neutral" on errors, and keeps the same public API as before.
    """

    def __init__(
        self,
        llm_url: str = "http://127.0.0.1:11434/api/generate",
        model: str = "qwen2.5-coder:7b",
        timeout: int = 120,
        retries: int = 1,
        llm_log_path: str | None = None,
    ):
        self.llm_url = llm_url
        self.model = model
        self.timeout = timeout
        self.retries = max(0, int(retries))
        # Instantiate the repo's LLMClient (backwards-compatible)
        try:
            self.client = LLMClient(
                base_url=self.llm_url,
                model=self.model,
                timeout=self.timeout,
                retries=self.retries,
                provider="ollama_local",
                api_key="",
                llm_log_path=llm_log_path,
            )
        except Exception as exc:
            logger.warning("Failed to create LLMClient in EmotionLlm: %s", exc)
            self.client = None

    def _normalize_label(self, label: str) -> str:
        if not label:
            return "neutral"
        lab = str(label).strip().lower()
        return lab if lab in EMOTION_LABELS else "neutral"

    def _parse_result_to_list(self, raw: object, count: int) -> List[str]:
        """
        Accepts multiple shapes and returns a list of emotion labels of length `count`.
        Supported shapes:
          - list of {"index": int, "emotion": "happy"} objects
          - list of emotion strings (ordered)
          - dict mapping index->emotion or {"emotions": [...]} or {"results": [...]}
        On any unexpected shape, returns neutral labels.
        """
        try:
            # If it's already a list of dicts with index/emotion
            if isinstance(raw, list):
                # list of dicts with index/emotion
                if all(isinstance(x, dict) and "index" in x and "emotion" in x for x in raw):
                    mapping = {int(x["index"]): self._normalize_label(x["emotion"]) for x in raw}
                    return [mapping.get(i, "neutral") for i in range(count)]

                # list of strings (ordered)
                if all(isinstance(x, str) for x in raw):
                    out = [self._normalize_label(x) for x in raw]
                    # If lengths mismatch, pad or trim
                    if len(out) < count:
                        out.extend(["neutral"] * (count - len(out)))
                    return out[:count]

                # list of dicts with 'emotion' key only (ordered)
                if all(isinstance(x, dict) and "emotion" in x for x in raw):
                    out = [self._normalize_label(x.get("emotion")) for x in raw]
                    if len(out) < count:
                        out.extend(["neutral"] * (count - len(out)))
                    return out[:count]

            # If it's a dict, try common wrappers
            if isinstance(raw, dict):
                # {"emotions": ["happy", ...]}
                if "emotions" in raw and isinstance(raw["emotions"], list):
                    return self._parse_result_to_list(raw["emotions"], count)

                # {"results": [...]}
                if "results" in raw and isinstance(raw["results"], list):
                    return self._parse_result_to_list(raw["results"], count)

                # mapping of index->emotion as strings or numbers
                # e.g., {"0": "happy", "1": "sad"} or {0: "happy"}
                keys = list(raw.keys())
                if keys and all(str(k).isdigit() for k in keys):
                    mapping = {int(k): self._normalize_label(raw[k]) for k in keys}
                    return [mapping.get(i, "neutral") for i in range(count)]

            # If nothing matched, fallback
            logger.debug("EmotionLlm: unrecognized raw shape: %s", type(raw))
        except Exception as exc:
            logger.debug("EmotionLlm: error parsing raw result: %s", exc)

        # Fallback: neutral labels
        return ["neutral"] * count

    def classify_batch(self, texts: List[str]) -> List[str]:
        """
        Classify emotion for each text in *texts*.
        Returns a list of emotion labels (one per input).
        Falls back to "neutral" on any error.
        """
        if not texts:
            return []

        # If client couldn't be created, return neutrals
        if not getattr(self, "client", None):
            logger.warning("EmotionLlm: no LLM client available, returning neutral labels")
            return ["neutral"] * len(texts)

        # Build a compact user payload: include index and truncated text to avoid huge prompts
        # Keep the format simple; the LLM client will wrap it appropriately.
        entries = [{"index": i, "text": (t or "")[:800]} for i, t in enumerate(texts)]
        user = json.dumps(entries, ensure_ascii=False)

        try:
            raw = self.client.generate_json(system=EMOTION_SYSTEM_PROMPT, user=user)
            # raw may be {} on failure (per LLMClient behavior)
            if not raw:
                logger.debug("EmotionLlm: LLM returned empty result, falling back to neutral")
                return ["neutral"] * len(texts)

            # Parse into list of labels
            labels = self._parse_result_to_list(raw, len(texts))
            # Ensure final normalization
            labels = [self._normalize_label(l) for l in labels]
            return labels
        except Exception as exc:
            logger.warning("Emotion LLM classification failed: %s", exc)
            return ["neutral"] * len(texts)
