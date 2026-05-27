"""LLM-powered dialogue parser for chapter segmentation and speaker metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ebook_app.services.dialogue_segmentation_service import DialogueSegmentationService
from ebook_app.services.llm_client import OllamaChatClient


@dataclass
class Segment:
    text: str
    type: Literal["dialogue", "thought", "narration"] = "narration"
    speaker: str = "narrator"
    gender: Literal["male", "female", "unknown"] = "unknown"
    speaker_confidence: float = 1.0
    gender_confidence: float = 0.0
    character_confidence: float = 1.0
    paragraph_id: str = ""

    @property
    def kind(self) -> str:
        return self.type


@dataclass
class DetectedCharacter:
    name: str
    gender: Literal["male", "female", "unknown"] = "unknown"
    confidence: float = 0.0


@dataclass
class ParseResult:
    segments: list[Segment]
    detected_characters: list[DetectedCharacter]


class DialogueParser:
    """LLM-backed chapter parser using chat endpoint segmentation contract."""

    _DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
    _DEFAULT_MODEL = "mistral:instruct"

    def __init__(
        self,
        *,
        ollama_url: str | None = None,
        model: str | None = None,
        timeout_s: int = 120,
        retries: int = 1,
        llm_mode: str = "full",
        llm_strict_quotes: bool = False,
        llm_log_path: str | None = None,
    ) -> None:
        self.ollama_url = self._normalize_chat_url(ollama_url or self._DEFAULT_OLLAMA_URL)
        self.model = (model or self._DEFAULT_MODEL).strip()
        self.timeout_s = int(timeout_s)
        self.retries = max(0, int(retries))
        self.llm_mode = (llm_mode or "full").strip().lower()
        self.llm_strict_quotes = bool(llm_strict_quotes)
        self.client = OllamaChatClient(
            model=self.model,
            url=self.ollama_url,
            timeout_s=self.timeout_s,
            retries=self.retries,
            log_path=llm_log_path,
        )
        self.service = DialogueSegmentationService(client=self.client, strict_quotes=self.llm_strict_quotes)

    @staticmethod
    def _normalize_chat_url(url: str) -> str:
        clean = (url or "").strip()
        if clean.endswith("/api/generate"):
            return clean[: -len("/api/generate")] + "/api/chat"
        return clean

    def parse(self, text: str, chapter_id: str = "ch") -> ParseResult:
        if self.llm_mode == "off":
            clean = self.service.clean_text_for_llm(text)
            return ParseResult(
                segments=[self._fallback_segment(clean, chapter_id, 0)],
                detected_characters=[],
            )

        result = self.service.parse(text=text, chapter_id=chapter_id)
        segments = [
            Segment(
                text=item.text,
                type=item.type,
                speaker=(item.speaker or "narrator"),
                gender="unknown",
                speaker_confidence=0.9 if item.speaker and item.speaker != "narrator" else 1.0,
                gender_confidence=0.0,
                character_confidence=0.7 if item.speaker and item.speaker != "narrator" else 1.0,
                paragraph_id=f"{chapter_id}_p{idx}",
            )
            for idx, item in enumerate(result.segments)
            if item.text.strip()
        ]
        if not segments:
            segments = [self._fallback_segment(self.service.clean_text_for_llm(text), chapter_id, 0)]

        detected_characters = [
            DetectedCharacter(name=name, gender="unknown", confidence=0.85)
            for name in result.characters
        ]
        return ParseResult(segments=segments, detected_characters=detected_characters)

    @staticmethod
    def _fallback_segment(text: str, chapter_id: str, index: int) -> Segment:
        return Segment(
            text=text,
            type="narration",
            speaker="narrator",
            gender="unknown",
            speaker_confidence=1.0,
            gender_confidence=0.0,
            character_confidence=1.0,
            paragraph_id=f"{chapter_id}_p{index}",
        )
