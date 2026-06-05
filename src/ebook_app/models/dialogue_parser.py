from __future__ import annotations

from dataclasses import asdict, dataclass

from ebook_app.characters.character_db import CharacterDatabase
from ebook_app.scraping.text_cleaner import TextCleaner
from ebook_app.services.dialogue_segmentation_service import DialogueSegmentationService
from ebook_app.services.llm_client import OllamaChatClient


@dataclass
class Segment:
    text: str
    speaker: str
    type: str
    gender: str
    speaker_confidence: float = 0.0
    gender_confidence: float = 0.0
    character_confidence: float = 0.0
    paragraph_id: str = ''


@dataclass
class DetectedCharacter:
    name: str
    gender: str = 'unknown'
    confidence: float = 0.0


@dataclass
class ParseResult:
    segments: list[Segment]
    detected_characters: list[DetectedCharacter]


class DialogueParser:
    def __init__(
        self,
        *,
        ollama_url: str = 'http://127.0.0.1:11434/api/generate',
        model: str | None = None,
        semantic_model: str | None = None,
        fallback_model: str | None = None,
        formatter_model: str | None = None,
        character_db: CharacterDatabase | None = None,
        llm_log_path: str | None = None,
        timeout: int = 300,
        retries: int = 1,
        max_context_tokens: int = 250_000,
    ) -> None:
        self.ollama_url = self._normalize_ollama_url(ollama_url)
        chosen = semantic_model or model or 'qwen2.5-coder:7b'
        self.model = chosen
        self.semantic_model = chosen
        self.fallback_model = chosen
        self.formatter_model = chosen
        self.character_db = character_db
        common = dict(base_url=self.ollama_url, timeout=timeout, retries=retries, max_context_tokens=max_context_tokens, llm_log_path=llm_log_path)
        self.client = OllamaChatClient(model=self.semantic_model, **common)
        self.fallback_client = OllamaChatClient(model=self.fallback_model, **common)
        self.formatter_client = OllamaChatClient(model=self.formatter_model, **common)
        self.service = DialogueSegmentationService(client=self.client, fallback_client=self.fallback_client, formatter_client=self.formatter_client)

    @staticmethod
    def _normalize_ollama_url(url: str) -> str:
        return url[:-len('/api/chat')] + '/api/generate' if url.endswith('/api/chat') else url

    @staticmethod
    def _clean_text(text: str) -> str:
        cleaned = TextCleaner.clean_text(text or '')
        lines = [line for line in cleaned.splitlines() if line.strip().casefold() not in {'next chapter', 'subscribe now'}]
        return '\n'.join(lines).strip()

    def _known_characters(self) -> list[dict]:
        if not self.character_db:
            return []
        return [asdict(char) for char in self.character_db.all()]

    def _canonicalize_name(self, name: str) -> tuple[str, str | None]:
        cleaned = (name or '').strip()
        while cleaned and cleaned[-1] in '.,!?;:':
            cleaned = cleaned[:-1].rstrip()
        lowered = cleaned.casefold()
        if lowered == 'unknown':
            return 'unknown', None
        if lowered == 'narrator':
            return 'narrator', None
        if self.character_db:
            resolved = self.character_db.resolve_name(cleaned)
            if resolved:
                return resolved.name, resolved.gender
        return cleaned or 'unknown', None

    def parse(self, text: str, chapter_id: str, manual_segment_hints=None) -> ParseResult:
        cleaned = self._clean_text(text)
        try:
            llm_result = self.service.parse(
                text=cleaned,
                chapter_id=chapter_id,
                known_characters=self._known_characters(),
                manual_segment_hints=manual_segment_hints,
            )
            segments = []
            for item in llm_result.segments:
                speaker, canonical_gender = self._canonicalize_name(item.speaker)
                segments.append(Segment(
                    text=item.text,
                    speaker=speaker,
                    type=item.type if item.type in {'dialogue', 'thought', 'narration'} else 'narration',
                    gender=canonical_gender or item.gender or 'unknown',
                    speaker_confidence=float(item.speaker_confidence or 0.0),
                    gender_confidence=float(item.gender_confidence or 0.0),
                    character_confidence=float(item.character_confidence or 0.0),
                    paragraph_id=item.paragraph_id,
                ))
            if not segments:
                raise ValueError('No segments returned')
            detected = []
            seen = set()
            for item in llm_result.detected_characters:
                name, canonical_gender = self._canonicalize_name(item.name)
                key = name.casefold()
                if not name or key in seen:
                    continue
                seen.add(key)
                detected.append(DetectedCharacter(name=name, gender=canonical_gender or item.gender or 'unknown', confidence=float(item.confidence or 0.0)))
            return ParseResult(segments=segments, detected_characters=detected)
        except Exception:
            return ParseResult(
                segments=[Segment(text=cleaned or text, speaker='narrator', type='narration', gender='unknown')],
                detected_characters=[],
            )
