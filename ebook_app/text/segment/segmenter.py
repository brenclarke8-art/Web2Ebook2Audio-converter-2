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
    _DELIMITER_PATTERNS = (
        ("double_quotes", re.compile(r'"([^"]+?)"', re.DOTALL)),
        ("single_quotes", re.compile(r"(?<!\w)'([^']+?)'(?!\w)", re.DOTALL)),
        ("square_brackets", re.compile(r'\[([^\[\]]+?)\]', re.DOTALL)),
        ("curly_braces", re.compile(r'\{([^{}]+?)\}', re.DOTALL)),
        ("angle_brackets", re.compile(r'<([^<>]+?)>', re.DOTALL)),
        ("parentheses", re.compile(r'\(([^()]+?)\)', re.DOTALL)),
    )
    _DEFAULT_DELIMITER_FILTERS = {
        "single_quotes": True,
        "double_quotes": True,
        "square_brackets": True,
        "curly_braces": True,
        "angle_brackets": True,
        "parentheses": True,
    }
    _VALID_DELIMITER_TYPES = {*_DEFAULT_DELIMITER_FILTERS.keys(), "none"}
    _CHARACTER_TYPES = {"character", "narrator", "unknown"}
    _PASS2_PROTOCOL_FIELDS = (
        "id",
        "source_id",
        "chunk_id",
        "text",
        "span_start",
        "span_end",
        "delimiter_type",
        "is_dialogue",
        "type",
        "speaker",
        "character_type",
        "confidence",
        "notes",
    )

    def __init__(
        self,
        *,
        client,
        fallback_client=None,
        formatter_client=None,
        delimited_text_only: bool = False,
        delimiter_filters: dict[str, bool] | None = None,
        pass2_batch_size: int = 0,
        protocol_retries: int = 1,
    ):
        self.client = client
        self.fallback_client = fallback_client
        self.formatter_client = formatter_client
        self.delimited_text_only = bool(delimited_text_only)
        merged_filters = dict(self._DEFAULT_DELIMITER_FILTERS)
        for key, value in (delimiter_filters or {}).items():
            if key in merged_filters:
                merged_filters[key] = bool(value)
        self.delimiter_filters = merged_filters
        self.pass2_batch_size = max(0, int(pass2_batch_size or 0))
        self.protocol_retries = max(0, int(protocol_retries or 0))

    @staticmethod
    def _clean_input_text(text: str) -> str:
        cleaned = TextCleaner.clean_text(text or '')
        lines = [line for line in cleaned.splitlines() if line.strip().casefold() not in _UI_NOISE_LINES]
        return '\n'.join(lines).strip()

    @classmethod
    def _extract_delimited_fragments(cls, text: str, delimiter_filters: dict[str, bool] | None = None) -> list[str]:
        if not text:
            return []
        active_filters = dict(cls._DEFAULT_DELIMITER_FILTERS)
        for key, value in (delimiter_filters or {}).items():
            if key in active_filters:
                active_filters[key] = bool(value)
        matches: list[tuple[int, str]] = []
        seen: set[tuple[int, str]] = set()
        for delimiter_key, pattern in cls._DELIMITER_PATTERNS:
            # Missing keys in partial/legacy configs default to enabled behavior.
            if not active_filters.get(delimiter_key, True):
                continue
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
    def _llm_text_for_segment(
        cls,
        text: str,
        delimited_text_only: bool,
        delimiter_filters: dict[str, bool] | None = None,
    ) -> str:
        if not delimited_text_only:
            return text
        fragments = cls._extract_delimited_fragments(text, delimiter_filters)
        return '\n'.join(fragments).strip()

    @classmethod
    def _detect_delimiter_type(cls, text: str) -> str:
        for delimiter_key, pattern in cls._DELIMITER_PATTERNS:
            if pattern.search(text or ""):
                return delimiter_key
        return "none"

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

    @staticmethod
    def _batch_items(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
        if size <= 0 or len(items) <= size:
            return [items]
        return [items[idx:idx + size] for idx in range(0, len(items), size)]

    def _normalize_protocol_candidate(
        self,
        item: Any,
        *,
        expected_id: str,
        source_text: str,
        chunk_id: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if not isinstance(item, dict):
            return None, "candidate is not an object"
        item_id = str(item.get("id", "")).strip()
        if item_id != expected_id:
            return None, f"id mismatch expected={expected_id} got={item_id or '<empty>'}"
        seg_type = self._normalize_type(item.get("type", "narration"))
        speaker_value = item.get("speaker", None)
        speaker = self._normalize_speaker(speaker_value, seg_type) if speaker_value is not None else None
        if speaker is None and seg_type == "narration":
            speaker = "narrator"

        # Strict protocol shape (backward-compatible normalization when old keys are returned).
        protocol = {
            "id": item_id,
            "chunk_id": str(item.get("chunk_id", chunk_id)).strip() or chunk_id,
            "source_id": str(item.get("source_id", item_id)).strip() or item_id,
            "text": str(item.get("text", source_text)).strip() or source_text,
            "span_start": item.get("span_start", None),
            "span_end": item.get("span_end", None),
            "delimiter_type": str(item.get("delimiter_type", self._detect_delimiter_type(source_text))).strip() or "none",
            "is_dialogue": bool(item.get("is_dialogue", seg_type in {"dialogue", "thought"})),
            "speaker": speaker,
            "character_type": str(item.get("character_type", "narrator" if seg_type == "narration" else "unknown")).strip().lower(),
            "confidence": float(item.get("confidence", 1.0) or 0.0),
            "notes": None if item.get("notes") is None else str(item.get("notes")),
            "type": seg_type,
        }
        if protocol["character_type"] not in self._CHARACTER_TYPES:
            return None, f"character_type '{protocol['character_type']}' must be one of {self._CHARACTER_TYPES}"
        if protocol["delimiter_type"] not in self._VALID_DELIMITER_TYPES:
            return None, "delimiter_type is invalid"
        if protocol["speaker"] is not None and not isinstance(protocol["speaker"], str):
            return None, "speaker must be string or null"
        if not 0.0 <= protocol["confidence"] <= 1.0:
            return None, "confidence must be within [0.0, 1.0]"
        if protocol["span_start"] is not None and not isinstance(protocol["span_start"], int):
            return None, "span_start must be integer or null"
        if protocol["span_end"] is not None and not isinstance(protocol["span_end"], int):
            return None, "span_end must be integer or null"
        if protocol["span_start"] is not None and protocol["span_end"] is not None:
            if protocol["span_end"] < protocol["span_start"]:
                return None, "span_end must be >= span_start"
        return protocol, None

    def _validate_pass2(
        self,
        payload: Any,
        expected_items: list[dict[str, Any]],
        chunk_id: str,
    ) -> tuple[list[dict[str, Any]] | None, bool, float, str | None]:
        # Unwrap {"segments": [...]} envelope before the single-object check so
        # that wrapped responses are not silently dropped when multiple IDs are
        # expected.
        if isinstance(payload, dict) and payload.keys() >= {'segments'}:
            payload = payload.get('segments')
        expected_ids = [item["id"] for item in expected_items]
        text_by_id = {item["id"]: item["text"] for item in expected_items}
        if isinstance(payload, dict):
            payload = [payload] if len(expected_ids) == 1 else None
        if not isinstance(payload, list):
            return None, True, 0.0, f"payload is not a list (got {type(payload).__name__})"
        normalized = []
        expected = set(expected_ids)
        seen = set()
        for item in payload:
            if not isinstance(item, dict):
                return None, True, 0.0, f"candidate is not an object (got {type(item).__name__})"
            item_id = str(item.get('id', '')).strip()
            if item_id not in expected or item_id in seen:
                return None, True, len(seen) / max(1, len(expected_ids)), f"unexpected or duplicate id: {item_id or '<empty>'}"
            seen.add(item_id)
            normalized_item, error = self._normalize_protocol_candidate(
                item,
                expected_id=item_id,
                source_text=text_by_id.get(item_id, ""),
                chunk_id=chunk_id,
            )
            if normalized_item is None:
                return None, True, len(seen) / max(1, len(expected_ids)), error
            normalized.append(normalized_item)
        if len(seen) != len(expected_ids):
            missing_ids = sorted(expected.difference(seen))
            return None, True, len(seen) / max(1, len(expected_ids)), f"missing ids in response: {missing_ids}"
        return normalized, False, 1.0, None

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
        pass2_batch_size: int | None = None,
        protocol_retries: int | None = None,
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
                llm_text = self._llm_text_for_segment(item['text'], self.delimited_text_only, self.delimiter_filters)
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
                f'Return JSON only where each item contains fields: {", ".join(self._PASS2_PROTOCOL_FIELDS)}.\n'
                'Rules: type=dialogue|thought|narration, delimiter_type=single_quotes|double_quotes|square_brackets|'
                'curly_braces|angle_brackets|parentheses|none, speaker is nullable string, '
                'character_type=character|narrator|unknown, confidence=0.0-1.0.'
            )
            if manual_segment_hints:
                pass2_system += f'\nManual hints: {json.dumps(manual_segment_hints, ensure_ascii=False)}'
            if not llm_prompt_items:
                for item in source_items:
                    all_segments.append(self._heuristic_segment(item['text'], item['id']))
                continue
            llm_prompt_ids = {item['id'] for item in llm_prompt_items}
            resolved_by_id: dict[str, dict[str, Any]] = {}
            effective_batch_size = int(pass2_batch_size if pass2_batch_size is not None else self.pass2_batch_size)
            effective_protocol_retries = int(protocol_retries if protocol_retries is not None else self.protocol_retries)
            pass2_batches = self._batch_items(llm_prompt_items, effective_batch_size)
            for batch_index, batch_items in enumerate(pass2_batches):
                user_payload = json.dumps(batch_items, ensure_ascii=False)
                expected_batch_ids = [item['id'] for item in batch_items]
                primary_raw = []
                normalized_items = None
                malformed = False
                ratio = 0.0
                validation_error = None
                for attempt in range(effective_protocol_retries + 1):
                    request_user = user_payload
                    request_chapter_id = (
                        f'{chunk_id}_p2'
                        if (batch_index == 0 and attempt == 0 and len(pass2_batches) == 1)
                        else f'{chunk_id}_p2b{batch_index}_r{attempt}'
                    )
                    if attempt > 0:
                        request_user = (
                            "Repair prior response to strict protocol JSON only.\n"
                            f"EXPECTED_IDS:{json.dumps(expected_batch_ids, ensure_ascii=False)}\n"
                            f"SOURCE_LIST:{json.dumps(batch_items, ensure_ascii=False)}\n"
                            f"INVALID_RESPONSE:{json.dumps(primary_raw, ensure_ascii=False)}\n"
                            "Each item must include: "
                            + ", ".join(self._PASS2_PROTOCOL_FIELDS)
                            + "."
                        )
                    try:
                        primary_raw = self._ask(self.client, system=pass2_system, user=request_user, chapter_id=request_chapter_id)
                    except Exception as exc:
                        primary_raw = []
                        diagnostics.llm_failures.append(f'{request_chapter_id}:{exc}')
                    normalized_items, malformed, ratio, validation_error = self._validate_pass2(primary_raw, batch_items, chunk_id)
                    if normalized_items is not None:
                        break
                matched_ratios.append(ratio)
                if normalized_items is None and self.fallback_client:
                    diagnostics.pass2_fallback_attempted = True
                    try:
                        fallback_raw = self._ask(
                            self.fallback_client,
                            system=pass2_system,
                            user=user_payload,
                            chapter_id=(
                                f'{chunk_id}_p2f'
                                if (batch_index == 0 and len(pass2_batches) == 1)
                                else f'{chunk_id}_p2f_b{batch_index}'
                            ),
                        )
                    except Exception as exc:
                        fallback_raw = []
                        diagnostics.llm_failures.append(f'{chunk_id}_p2f_b{batch_index}:{exc}')
                    normalized_items, malformed, ratio, validation_error = self._validate_pass2(fallback_raw, batch_items, chunk_id)
                    matched_ratios[-1] = ratio
                    if normalized_items is not None:
                        diagnostics.pass2_fallback_used = True
                if normalized_items is None and self.formatter_client:
                    diagnostics.repair_attempted = True
                    repair_user = (
                        'Repair malformed pass-2 JSON.\n'
                        f'SOURCE LIST:\n{json.dumps(batch_items, ensure_ascii=False)}\n'
                        f'MALFORMED RESPONSE:\n{json.dumps(primary_raw, ensure_ascii=False)}\n'
                        'Return JSON array only with strict candidate fields.'
                    )
                    try:
                        repaired_raw = self._ask(
                            self.formatter_client,
                            system='Repair malformed pass-2 output.',
                            user=repair_user,
                            chapter_id=(
                                f'{chunk_id}_p2r'
                                if (batch_index == 0 and len(pass2_batches) == 1)
                                else f'{chunk_id}_p2r_b{batch_index}'
                            ),
                        )
                    except Exception as exc:
                        repaired_raw = []
                        diagnostics.llm_failures.append(f'{chunk_id}_p2r_b{batch_index}:{exc}')
                    normalized_items, malformed, ratio, validation_error = self._validate_pass2(repaired_raw, batch_items, chunk_id)
                    matched_ratios[-1] = ratio
                    if normalized_items is not None:
                        diagnostics.repair_succeeded = True
                if normalized_items is None:
                    diagnostics.validation_passed = False
                    diagnostics.needs_review = True
                    diagnostics.malformed_json = diagnostics.malformed_json or bool(malformed)
                    diagnostics.fallback_count += len(batch_items)
                    if validation_error:
                        diagnostics.llm_failures.append(f'{chunk_id}_p2_validation_b{batch_index}:{validation_error}')
                    for item in batch_items:
                        heuristic_seg = self._heuristic_segment(item["text"], item["id"])
                        resolved_by_id[item["id"]] = {
                            "id": item["id"],
                            "text": item["text"],
                            "type": heuristic_seg.type,
                            "speaker": heuristic_seg.speaker,
                            "chunk_id": chunk_id,
                            "source_id": item["id"],
                            "span_start": None,
                            "span_end": None,
                            "delimiter_type": self._detect_delimiter_type(item["text"]),
                            "is_dialogue": False,
                            "character_type": "unknown",
                            "confidence": 0.0,
                            "notes": "heuristic fallback",
                        }
                    continue
                for entry in normalized_items:
                    resolved_by_id[entry['id']] = entry
            for prompt_item in source_items:
                if prompt_item['id'] not in llm_prompt_ids:
                    all_segments.append(self._heuristic_segment(prompt_item['text'], prompt_item['id']))
                    continue
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

        # Drop segments with empty/whitespace text and guarantee every segment
        # has a non-empty speaker and a valid type.
        final_segments: list[DialogueLLMSegment] = []
        for seg in all_segments:
            if not (seg.text or '').strip():
                continue
            seg_type = self._normalize_type(seg.type)
            seg_speaker = self._normalize_speaker(seg.speaker, seg_type)
            final_segments.append(
                DialogueLLMSegment(
                    text=seg.text,
                    type=seg_type,
                    speaker=seg_speaker,
                    gender=seg.gender,
                    speaker_confidence=seg.speaker_confidence,
                    gender_confidence=seg.gender_confidence,
                    character_confidence=seg.character_confidence,
                    paragraph_id=seg.paragraph_id,
                )
            )

        return DialogueLLMResult(final_segments, list(characters_by_name.values()), diagnostics)
