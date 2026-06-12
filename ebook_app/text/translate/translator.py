# ebook_app/text/translate/translator.py
"""Translation engine — wraps LLM or cloud translation APIs."""
from __future__ import annotations
import logging
from typing import Optional

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
        llm_url: str = "http://127.0.0.1:11434/api/generate",
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

    def translate(self, text: str) -> str:
        """Translate *text* and return the translated string."""
        if not text.strip():
            return text
        if self.provider == "llm":
            return self._translate_llm(text)
        if self.provider in ("deepl", "google"):
            return self._translate_cloud(text)
        raise ValueError(f"Unknown translation provider: {self.provider!r}")

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

    def _translate_cloud(self, text: str) -> str:
        try:
            from deep_translator import GoogleTranslator, DeeplTranslator
        except ImportError as exc:
            raise ImportError("deep-translator is required for cloud translation") from exc
        if self.provider == "google":
            return GoogleTranslator(source=self.source_language, target=self.target_language).translate(text)
        return DeeplTranslator(api_key=self.api_key, source=self.source_language, target=self.target_language).translate(text)
