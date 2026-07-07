# ebook_app/text/segment/segmenter.py
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ebook_app.text.parse.html_cleaner import TextCleaner

_UI_NOISE_LINES = {'next chapter', 'subscribe now'}


@dataclass
class DialogueLLMSegment:
    text: str
    type: str
    speaker: str
    gender: str = 'unknown'
    speaker_confidence: float = 0.0
    gender_confidence: float = 0.0
    character_confidence: float = 0.0
    paragraph_id: str = ''


@dataclass
class DialogueDetectedCharacter:
    name: str
    gender: str = 'unknown'
    confidence: float = 0.0


@dataclass
class ParseDiagnostics:
    chunk_count: int = 0
    llm_failures: list[str] = field(default_factory=list)
    repair_attempted: bool = False
    repair_succeeded: bool = False
    validation_passed: bool = True
    needs_review: bool = False
    fallback_count: int = 0
    pass1_fallback_attempted: bool = False
    pass1_fallback_used: bool = False
    pass2_fallback_attempted: bool = False
    pass2_fallback_used: bool = False
    malformed_json: bool = False
    id_match_ratio: float = 1.0


@dataclass
class DialogueLLMResult:
    segments: list[DialogueLLMSegment]
    detected_characters: list[DialogueDetectedCharacter]
    diagnostics: ParseDiagnostics = field(default_factory=ParseDiagnostics)

    @property
    def characters(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.detected_characters]


class DialogueSegmentationService:
    _DELIMITED_PATTERNS = (
        re.compile(r'"([^"]+?)"', re.DOTALL),
        re.compile(r"(?<!\w)'([^']+?)'(?!\w)", re.DOTALL),
        re.compile(r'\[([^\[\]]+?)\]', re.DOTALL),
        re.compile(r'\{([^{}]+?)\}', re.DOTALL),
        re.compile(r'<([^<>]+?)>', re.DOTALL),
        re.compile(r'\(([^()]+?)\)', re.DOTALL),
    )

    def __init__(self, *, client, fallback_client=None, formatter_client=None, delimited_text_only: bool = False):
        self.client = client
        self.fallback_client = fallback_client
        self.formatter_client = formatter_client
        self.delimited_text_only = bool(delimited_text_only)

    @staticmethod
    def _clean_input_text(text: str) -> str:
        cleaned = TextCleaner.clean_text(text or '')
        lines = [line for line in cleaned.splitlines() if line.strip().casefold() not in _UI_NOISE_LINES]
        return '\n'.join(lines).strip()

    @classmethod
    def _extract_delimited_fragments(cls, text: str) -> list[str]:
        if not text:
            return []
        matches: list[tuple[int, str]] = []
        seen: set[tuple[int, str]] = set()
        for pattern in cls._DELIMITED_PATTERNS:
            for match in pattern.finditer(text):
                fragment = (match.group(1) or '').strip()
                if not fragment:
                    continue
                key = (match.start(), fragment)
                if key in seen:
                    continue
                seen.add(key)
                matches.append(key)
        matches.sort(key=lambda item: item[0])
        return [fragment for _, fragment in matches]

    @classmethod
    def _llm_text_for_segment(cls, text: str, delimited_text_only: bool) -> str:
        if not delimited_text_only:
            return text
        fragments = cls._extract_delimited_fragments(text)
        return '\n'.join(fragments).strip()

    @staticmethod
    def _split_chunks(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
        if not text:
            return ['']
        if len(text) <= chunk_size:
            return [text]
        out = []
        start = 0
        step = max(1, chunk_size - max(0, chunk_overlap))
        while start < len(text):
            chunk = text[start:start + chunk_size]
            if chunk:
                out.append(chunk)
            if start + chunk_size >= len(text):
                break
            start += step
        return out

    @staticmethod
    def _paragraphs(chunk: str) -> list[str]:
        parts = [p.strip() for p in re.split(r'\n\s*\n|\n', chunk) if p.strip()]
        return parts or ([chunk.strip()] if chunk.strip() else [])

    @staticmethod
    def _normalize_type(value: str) -> str:
        lowered = (value or '').strip().lower()
        return lowered if lowered in {'dialogue', 'thought', 'narration'} else 'narration'

    @staticmethod
    def _normalize_gender(value: str) -> str:
        lowered = (value or '').strip().lower()
        return lowered if lowered in {'male', 'female'} else 'unknown'

    @staticmethod
    def _normalize_speaker(value: str, segment_type: str) -> str:
        speaker = (value or '').strip()
        while speaker and speaker[-1] in '.,!?;:':
            speaker = speaker[:-1].rstrip()
        lowered = speaker.casefold()
        if not speaker:
            return 'narrator' if segment_type == 'narration' else 'unknown'
        if lowered == 'narrator':
            return 'narrator'
        if lowered == 'unknown':
            return 'unknown'
        return speaker

    @staticmethod
    def _heuristic_segment(paragraph: str, paragraph_id: str) -> DialogueLLMSegment:
        stripped = paragraph.strip()
        seg_type = 'dialogue' if stripped.startswith(('"', '“', '\'')) and stripped.endswith(('"', '”', '\'')) else 'narration'
        speaker = 'unknown' if seg_type != 'narration' else 'narrator'
        return DialogueLLMSegment(text=stripped, type=seg_type, speaker=speaker, paragraph_id=paragraph_id)

    @staticmethod
    def _format_known_character_context(known_characters) -> str:
        if not known_characters:
            return ''
        lines = ['KNOWN CHARACTER CONTEXT (canonical names):']
        for char in known_characters:
            if not isinstance(char, dict):
                continue
            aliases = ', '.join(char.get('aliases', []) or []) or '-'
            gender = char.get('gender', 'unknown') or 'unknown'
            description = char.get('description', '') or ''
            lines.append(f"{char.get('name', '')} | aliases={aliases} | gender={gender} | description={description}")
        return '\n'.join(lines)

    @staticmethod
    def _extract_summary(payload: Any) -> str:
        return payload.get('summary', '') if isinstance(payload, dict) else ''

    @staticmethod
    def _normalize_character_payload(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            return []
        out = []
        for item in payload:
            if not isinstance(item, dict) or not item.get('name'):
                continue
            out.append({
                'name': str(item.get('name', '')).strip(),
                'gender': DialogueSegmentationService._normalize_gender(item.get('gender', 'unknown')),
                'confidence': float(item.get('confidence', 0.0) or 0.0),
            })
        return out

    @staticmethod
    def _suspiciously_weak(primary: list[dict[str, Any]], summary: str) -> bool:
        hinted_names = {name for name in re.findall(r'\b[A-Z][a-z]+\b', summary or '') if name.lower() not in {'you', 'the'}}
        return bool(hinted_names) and len(primary) <= 1 and len(hinted_names) > len(primary) + 1

    def _ask(self, client, *, system: str, user: str, chapter_id: str):
        if client is None:
            return []
        if hasattr(client, 'ask_json_any'):
            return client.ask_json_any(system=system, user=user, chapter_id=chapter_id)
        return client.ask_json(system=system, user=user, chapter_id=chapter_id)

    def _validate_pass2(self, payload: Any, expected_ids: list[str]) -> tuple[list[dict[str, Any]] | None, bool, float]:
        if isinstance(payload, dict):
            payload = [payload] if len(expected_ids) == 1 else None
        if isinstance(payload, dict) and payload.keys() >= {'segments'}:
            payload = payload.get('segments')
        if not isinstance(payload, list):
            return None, True, 0.0
        normalized = []
        expected = set(expected_ids)
        seen = set()
        for item in payload:
            if not isinstance(item, dict):
                return None, True, 0.0
            item_id = str(item.get('id', '')).strip()
            if item_id not in expected or item_id in seen:
                return None, True, len(seen) / max(1, len(expected_ids))
            seen.add(item_id)
            normalized.append({
                'id': item_id,
                'type': self._normalize_type(item.get('type', 'narration')),
                'speaker': self._normalize_speaker(item.get('speaker', ''), self._normalize_type(item.get('type', 'narration'))),
            })
        if len(seen) != len(expected_ids):
            return None, True, len(seen) / max(1, len(expected_ids))
        return normalized, False, 1.0

    def parse(
        self,
        *,
        text: str,
        chapter_id: str,
        known_characters=None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        manual_segment_hints=None,
        story_context_block: str | None = None,
    ) -> DialogueLLMResult:
        cleaned = self._clean_input_text(text)
        chunks = self._split_chunks(cleaned, int(chunk_size or 6000), int(chunk_overlap or 500))
        diagnostics = ParseDiagnostics(chunk_count=len(chunks))
        characters_by_name: dict[str, DialogueDetectedCharacter] = {}
        all_segments: list[DialogueLLMSegment] = []
        known_context = self._format_known_character_context(known_characters)
        matched_ratios: list[float] = []

        for idx, chunk in enumerate(chunks):
            chunk_id = chapter_id if len(chunks) == 1 else f'{chapter_id}_c{idx + 1}'
            source_items = [{'id': f'{chunk_id}_p{i}', 'text': paragraph} for i, paragraph in enumerate(self._paragraphs(chunk))]
            llm_prompt_items = []
            for item in source_items:
                llm_text = self._llm_text_for_segment(item['text'], self.delimited_text_only)
                if not llm_text:
                    continue
                llm_prompt_items.append({'id': item['id'], 'text': llm_text})
            llm_chunk = '\n'.join(item['text'] for item in llm_prompt_items).strip()
            summary_system = 'You are a chapter-summary assistant. Return JSON object {"summary": "..."} only.'
            if llm_chunk:
                try:
                    summary_payload = self._ask(self.client, system=summary_system, user=llm_chunk, chapter_id=f'{chunk_id}_p0')
                except Exception as exc:
                    summary_payload = {}
                    diagnostics.llm_failures.append(f'{chunk_id}_p0:{exc}')
            else:
                summary_payload = {}
            summary = self._extract_summary(summary_payload)

            pass1_system = (
                'You are a deterministic character-extraction engine.\n'
                'CHARACTER DETECTION\n'
                'Return JSON only using this shape:\n'
                '[{ "name": "...", "gender": "male|female|unknown", "confidence": 0.0-1.0 }]'
            )
            if story_context_block:
                pass1_system += f'\n{story_context_block}'
            if known_context:
                pass1_system += f'\nCONTEXT (from previous chapters):\n{known_context}'
            if llm_chunk:
                try:
                    pass1_payload = self._ask(self.client, system=pass1_system, user=llm_chunk, chapter_id=f'{chunk_id}_p1')
                except Exception as exc:
                    pass1_payload = []
                    diagnostics.llm_failures.append(f'{chunk_id}_p1:{exc}')
            else:
                pass1_payload = []
            pass1_chars = self._normalize_character_payload(pass1_payload)
            if llm_chunk and self.fallback_client and self._suspiciously_weak(pass1_chars, summary):
                diagnostics.pass1_fallback_attempted = True
                try:
                    fallback_chars = self._normalize_character_payload(
                        self._ask(self.fallback_client, system=pass1_system, user=llm_chunk, chapter_id=f'{chunk_id}_p1f')
                    )
                except Exception as exc:
                    fallback_chars = []
                    diagnostics.llm_failures.append(f'{chunk_id}_p1f:{exc}')
                if len(fallback_chars) > len(pass1_chars):
                    pass1_chars = fallback_chars
                    diagnostics.pass1_fallback_used = True
            for item in pass1_chars:
                key = item['name'].casefold()
                candidate = DialogueDetectedCharacter(**item)
                existing = characters_by_name.get(key)
                if existing is None or candidate.confidence >= existing.confidence:
                    characters_by_name[key] = candidate

            pass2_system = (
                'SEGMENT AND ATTRIBUTE\n'
                'Input: JSON array of {"id": "...", "text": "..."}\n'
                'Return JSON only as:\n'
                '[{"id": "...", "type": "dialogue|thought|narration", "speaker": "Name or narrator"}]'
            )
            if manual_segment_hints:
                pass2_system += f'\nManual hints: {json.dumps(manual_segment_hints, ensure_ascii=False)}'
            if not llm_prompt_items:
                for item in source_items:
                    all_segments.append(self._heuristic_segment(item['text'], item['id']))
                continue
            user_payload = json.dumps(llm_prompt_items, ensure_ascii=False)
            try:
                primary_raw = self._ask(self.client, system=pass2_system, user=user_payload, chapter_id=f'{chunk_id}_p2')
            except Exception as exc:
                primary_raw = []
                diagnostics.llm_failures.append(f'{chunk_id}_p2:{exc}')
            normalized_items, malformed, ratio = self._validate_pass2(primary_raw, [item['id'] for item in llm_prompt_items])
            matched_ratios.append(ratio)
            if normalized_items is None and self.fallback_client:
                diagnostics.pass2_fallback_attempted = True
                try:
                    fallback_raw = self._ask(self.fallback_client, system=pass2_system, user=user_payload, chapter_id=f'{chunk_id}_p2f')
                except Exception as exc:
                    fallback_raw = []
                    diagnostics.llm_failures.append(f'{chunk_id}_p2f:{exc}')
                normalized_items, malformed, ratio = self._validate_pass2(fallback_raw, [item['id'] for item in llm_prompt_items])
                matched_ratios[-1] = ratio
                if normalized_items is not None:
                    diagnostics.pass2_fallback_used = True
            if normalized_items is None and self.formatter_client:
                diagnostics.repair_attempted = True
                repair_user = (
                    'Repair malformed pass-2 JSON.\n'
                    f'SOURCE LIST:\n{json.dumps(llm_prompt_items, ensure_ascii=False)}\n'
                    f'MALFORMED RESPONSE:\n{json.dumps(primary_raw, ensure_ascii=False)}'
                )
                try:
                    repaired_raw = self._ask(self.formatter_client, system='Repair malformed pass-2 output.', user=repair_user, chapter_id=f'{chunk_id}_p2r')
                except Exception as exc:
                    repaired_raw = []
                    diagnostics.llm_failures.append(f'{chunk_id}_p2r:{exc}')
                normalized_items, malformed, ratio = self._validate_pass2(repaired_raw, [item['id'] for item in llm_prompt_items])
                matched_ratios[-1] = ratio
                if normalized_items is not None:
                    diagnostics.repair_succeeded = True
            if normalized_items is None:
                diagnostics.validation_passed = False
                diagnostics.needs_review = True
                diagnostics.malformed_json = True or malformed
                diagnostics.fallback_count += len(llm_prompt_items)
                for item in source_items:
                    all_segments.append(self._heuristic_segment(item['text'], item['id']))
                continue
            resolved_by_id = {entry['id']: entry for entry in normalized_items}
            for prompt_item in source_items:
                resolved = resolved_by_id.get(prompt_item['id'])
                if resolved is None:
                    all_segments.append(self._heuristic_segment(prompt_item['text'], prompt_item['id']))
                    continue
                all_segments.append(
                    DialogueLLMSegment(
                        text=prompt_item['text'],
                        type=resolved['type'],
                        speaker=resolved['speaker'],
                        paragraph_id=prompt_item['id'],
                    )
                )

        if matched_ratios:
            diagnostics.id_match_ratio = sum(matched_ratios) / len(matched_ratios)
        return DialogueLLMResult(all_segments, list(characters_by_name.values()), diagnostics)
