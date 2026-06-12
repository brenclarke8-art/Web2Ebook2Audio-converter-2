# ebook_app/text/identify/speaker_llm.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests


class OllamaChatClient:
    def __init__(
        self,
        *,
        base_url: str = 'http://127.0.0.1:11434/api/generate',
        model: str = 'qwen2.5-coder:7b',
        max_context_tokens: int = 250_000,
        timeout: int = 300,
        retries: int = 1,
        llm_log_path: str | None = None,
    ) -> None:
        self.base_url = base_url
        self.model = model
        self.max_context_tokens = int(max_context_tokens)
        self.timeout = int(timeout)
        self.retries = max(1, int(retries))
        self.llm_log_path = Path(llm_log_path) if llm_log_path else None

    def _log(self, record: dict[str, Any]) -> None:
        if not self.llm_log_path:
            return
        self.llm_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.llm_log_path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')

    @staticmethod
    def _parse_json_text(raw: Any) -> Any:
        if isinstance(raw, (dict, list)):
            return raw
        text = '' if raw is None else str(raw).strip()
        if text.startswith('```'):
            lines = text.splitlines()
            if lines and lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            text = '\n'.join(lines).strip()
        return json.loads(text)

    def ask_json_any(self, *, system: str, user: str, chapter_id: str) -> Any:
        payload = {
            'model': self.model,
            'prompt': f'{system}\n\n{user}',
            'system': system,
            'stream': False,
            'options': {'num_ctx': self.max_context_tokens},
        }
        last_error: Exception | None = None
        for _attempt in range(self.retries):
            try:
                response = requests.post(self.base_url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                body = response.json()
                raw = body.get('response', '')
                parsed = self._parse_json_text(raw)
                self._log({'chapter_id': chapter_id, 'request': payload, 'response_raw': raw})
                return parsed
            except Exception as exc:
                last_error = exc
                self._log({'chapter_id': chapter_id, 'request': payload, 'error': str(exc)})
        assert last_error is not None
        raise last_error

    def ask_json(self, *, system: str, user: str, chapter_id: str) -> Any:
        return self.ask_json_any(system=system, user=user, chapter_id=chapter_id)


# --- DialogueParser (migrated from models/dialogue_parser.py) ---

from dataclasses import asdict, dataclass

from ebook_app.app.state.character_db import CharacterDatabase
from ebook_app.text.parse.html_cleaner import TextCleaner
from ebook_app.text.segment.segmenter import DialogueSegmentationService


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
