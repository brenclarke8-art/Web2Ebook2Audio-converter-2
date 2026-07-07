# ebook_app/text/translate/translator.py
"""Translation engine — wraps LLM or cloud translation APIs."""
from __future__ import annotations
import logging
from typing import Optional, List

import requests

logger = logging.getLogger(__name__)


class Translator:
    """
    Translate text using an LLM or a machine-translation API.

    Providers:
        "llm"   — local Ollama/OpenAI-compatible endpoint
        "deepl" — DeepL API (requires deep-translator)
        "google"— Google Translate (requires deep-translator)
    """

    def __init__(
        self,
        provider: str = "llm",
        target_language: str = "en",
        source_language: str = "auto",
        llm_url: str = "http://127.0.0.1:11434/api/chat",
        llm_model: str = "qwen2.5-coder:7b",
        api_key: Optional[str] = None,
        timeout: int = 120,
    ):
        self.provider = provider
        self.target_language = target_language
        self.source_language = source_language
        self.llm_url = llm_url
        self.llm_model = llm_model
        self.api_key = api_key
        self.timeout = timeout

        # Best-effort automatic model detection when requested
        if self.provider == "llm" and (not self.llm_model or self.llm_model.strip().lower() == "auto"):
            self.llm_model = self._detect_default_model(self.llm_url) or "qwen2.5-coder:7b"

    def _detect_default_model(self, base_url: str) -> Optional[str]:
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
            logger.debug("Translator: automatic model detection failed: %s", exc)
        return None

    def translate(self, text: str) -> str:
        """Translate *text* and return the translated string."""
        if not text.strip():
            return text
        if self.provider == "llm":
            return self._translate_llm_batched(text)
        if self.provider in ("deepl", "google"):
            return self._translate_cloud(text)
        raise ValueError(f"Unknown translation provider: {self.provider!r}")

    # -------------------------
    # LLM translation with batch splitting
    # -------------------------
    def _translate_llm_batched(self, text: str) -> str:
        # Simple heuristic: if text is short, do single call
        if len(text) <= 4000:
            return self._translate_llm(text)

        # Split by paragraphs to keep semantics
        paragraphs = [p for p in text.split("\n") if p.strip()]
        if len(paragraphs) == 1:
            # Fallback: split by chunks of ~2000 chars
            chunks: List[str] = []
            buf = text
            while buf:
                chunks.append(buf[:2000])
                buf = buf[2000:]
        else:
            chunks = paragraphs

        translated_chunks: List[str] = []
        for chunk in chunks:
            try:
                translated = self._translate_llm(chunk)
                if not translated.strip():
                    # If LLM returns empty, keep original chunk to avoid data loss
                    translated = chunk
                translated_chunks.append(translated)
            except Exception as exc:
                logger.warning("Translator: LLM chunk translation failed, using original chunk: %s", exc)
                translated_chunks.append(chunk)

        # Reassemble with newlines to preserve structure
        return "\n".join(translated_chunks)

    def _translate_llm(self, text: str) -> str:
        from ebook_app.text.identify.speaker_llm import OllamaChatClient
        from ebook_app.text.translate.prompt_templates import TRANSLATION_SYSTEM_PROMPT

        client = OllamaChatClient(
            base_url=self.llm_url,
            model=self.llm_model,
            timeout=self.timeout,
        )
        system = TRANSLATION_SYSTEM_PROMPT.format(
            target_language=self.target_language,
            source_language=self.source_language,
        )
        result = client.ask_json_any(system=system, user=text, chapter_id="translation")
        if isinstance(result, dict):
            return result.get("translation", text)
        return str(result)

    # -------------------------
    # Cloud translation
    # -------------------------
    def _translate_cloud(self, text: str) -> str:
        try:
            from deep_translator import GoogleTranslator, DeeplTranslator
        except ImportError as exc:
            raise ImportError("deep-translator is required for cloud translation") from exc
        if self.provider == "google":
            return GoogleTranslator(source=self.source_language, target=self.target_language).translate(text)
        return DeeplTranslator(api_key=self.api_key, source=self.source_language, target=self.target_language).translate(text)
