"""LLM-based emotion classification for text segments."""
from __future__ import annotations

import json
import logging
from typing import List

import requests

from ebook_app.text.identify.llm_client import LLMClient

logger = logging.getLogger(__name__)

EMOTION_SYSTEM_PROMPT = """You are an expert literary analyst. For each text segment provided, identify the dominant emotion.
Choose from: neutral, happy, sad, angry, fearful, surprised, disgusted, whispering.
Return a JSON array where each element has keys "index" and "emotion".
"""

EMOTION_LABELS = ["neutral", "happy", "sad", "angry", "fearful", "surprised", "disgusted", "whispering"]


class EmotionLlm:
    """Classify emotion for a batch of text segments using an LLM.

    - Uses LLMClient (safe requests.post, 404 chat fallback).
    - Adds structured JSONL-style logging via LLMClient.llm_log_path.
    - Adds best-effort automatic model detection when model == "auto".
    - Defensive parsing: falls back to "neutral" on errors.
    """

    def __init__(
        self,
        llm_url: str = "http://127.0.0.1:11434/api/chat",
        model: str = "qwen2.5-coder:7b",
        timeout: int = 120,
        retries: int = 1,
        llm_log_path: str | None = None,
    ):
        self.llm_url = llm_url
        self.model = model
        self.timeout = timeout
        self.retries = max(0, int(retries))

        # Best-effort automatic model detection
        if not self.model or self.model.strip().lower() == "auto":
            self.model = self._detect_default_model(self.llm_url) or "qwen2.5-coder:7b"

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

    def _detect_default_model(self, base_url: str) -> str | None:
        """Best-effort: query Ollama for available models and pick the first."""
        try:
            root = base_url.split("/api", 1)[0].rstrip("/")
            resp = requests.get(root + "/api/tags", timeout=3)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models") or []
            if models and isinstance(models, list):
                first = models[0]
                if isinstance(first, dict):
                    return first.get("name") or first.get("model")
        except Exception as exc:
            logger.debug("EmotionLlm: automatic model detection failed: %s", exc)
        return None

    def _normalize_label(self, label: str) -> str:
        if not label:
            return "neutral"
        lab = str(label).strip().lower()
        return lab if lab in EMOTION_LABELS else "neutral"

    def _parse_result_to_list(self, raw: object, count: int) -> List[str]:
        try:
            if isinstance(raw, list):
                if all(isinstance(x, dict) and "index" in x and "emotion" in x for x in raw):
                    mapping = {int(x["index"]): self._normalize_label(x["emotion"]) for x in raw}
                    return [mapping.get(i, "neutral") for i in range(count)]

                if all(isinstance(x, str) for x in raw):
                    out = [self._normalize_label(x) for x in raw]
                    if len(out) < count:
                        out.extend(["neutral"] * (count - len(out)))
                    return out[:count]

                if all(isinstance(x, dict) and "emotion" in x for x in raw):
                    out = [self._normalize_label(x.get("emotion")) for x in raw]
                    if len(out) < count:
                        out.extend(["neutral"] * (count - len(out)))
                    return out[:count]

            if isinstance(raw, dict):
                if "emotions" in raw and isinstance(raw["emotions"], list):
                    return self._parse_result_to_list(raw["emotions"], count)

                if "results" in raw and isinstance(raw["results"], list):
                    return self._parse_result_to_list(raw["results"], count)

                keys = list(raw.keys())
                if keys and all(str(k).isdigit() for k in keys):
                    mapping = {int(k): self._normalize_label(raw[k]) for k in keys}
                    return [mapping.get(i, "neutral") for i in range(count)]

            logger.debug("EmotionLlm: unrecognized raw shape: %s", type(raw))
        except Exception as exc:
            logger.debug("EmotionLlm: error parsing raw result: %s", exc)

        return ["neutral"] * count

    def classify_batch(self, texts: List[str]) -> List[str]:
        if not texts:
            return []

        if not getattr(self, "client", None):
            logger.warning("EmotionLlm: no LLM client available, returning neutral labels")
            return ["neutral"] * len(texts)

        entries = [{"index": i, "text": (t or "")[:800]} for i, t in enumerate(texts)]
        user = json.dumps(entries, ensure_ascii=False)

        try:
            raw = self.client.generate_json(system=EMOTION_SYSTEM_PROMPT, user=user)
            if not raw:
                logger.debug("EmotionLlm: LLM returned empty result, falling back to neutral")
                return ["neutral"] * len(texts)

            labels = self._parse_result_to_list(raw, len(texts))
            labels = [self._normalize_label(l) for l in labels]
            return labels
        except Exception as exc:
            logger.warning("Emotion LLM classification failed: %s", exc)
            return ["neutral"] * len(texts)
