# src/ebook_app/models/dialogue_parser.py
"""LLM-powered dialogue parser for chapter segmentation and speaker metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Literal

import requests

logger = logging.getLogger(__name__)


@dataclass
class Segment:
    """A single segmented unit from chapter text.

    :param text:        The raw text content.
    :param type:        ``'dialogue'`` | ``'thought'`` | ``'narration'``.
    :param speaker:     Speaker name, or ``'narrator'`` for non-dialogue text.
    :param gender:      ``'male'`` | ``'female'`` | ``'unknown'``.
    :param speaker_confidence: Confidence for speaker attribution in [0.0, 1.0].
    :param gender_confidence:  Confidence for gender inference in [0.0, 1.0].
    :param character_confidence: Confidence this segment belongs to the character in [0.0, 1.0].
    :param paragraph_id: Unique identifier for SMIL synchronisation.
    """

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
        """Backward-compatible alias for older callers expecting ``kind``."""
        return self.type


@dataclass
class DetectedCharacter:
    """Character candidate detected by the LLM."""

    name: str
    gender: Literal["male", "female", "unknown"] = "unknown"
    confidence: float = 0.0


@dataclass
class ParseResult:
    """Structured parse output for a chapter."""

    segments: list[Segment]
    detected_characters: list[DetectedCharacter]


class DialogueParser:
    """LLM-backed chapter parser using a strict JSON output contract."""

    _DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
    _DEFAULT_MODEL = "mistral"
    _ALLOWED_TYPES = {"dialogue", "thought", "narration"}
    _ALLOWED_GENDERS = {"male", "female", "unknown"}
    _UI_NOISE_PATTERNS = (
        r"\bnext\s+chapter\b",
        r"\bprevious\s+chapter\b",
        r"\btable\s+of\s+contents\b",
        r"\bchapter\s+list\b",
        r"\bmenu\b",
        r"\bnavigation\b",
        r"\bskip\s+to\s+content\b",
        r"\bsubscribe\b",
        r"\blog[\s-]?in\b",
        r"\bsign[\s-]?in\b",
        r"\bsign[\s-]?up\b",
        r"\bcomment(s)?\b",
        r"\bshare\b",
        r"\breport\b",
        r"\badvertisement\b",
        r"^ad[s]?\b",
        r"\bpatreon\b",
        r"\bdiscord\b",
    )

    def __init__(
        self,
        *,
        ollama_url: str | None = None,
        model: str | None = None,
        timeout_s: int = 120,
        llm_log_path: Path | str | None = None,
    ) -> None:
        self.ollama_url = (ollama_url or self._DEFAULT_OLLAMA_URL).strip()
        self.model = (model or self._DEFAULT_MODEL).strip()
        self.timeout_s = timeout_s
        self.llm_log_path = Path(llm_log_path) if llm_log_path else None

    def parse(self, text: str, chapter_id: str = "ch") -> ParseResult:
        """Parse *text* via Ollama and return validated segments/characters."""
        source_text = (text or "").strip()
        cleaned_text = self._clean_text_for_llm(source_text)
        if not cleaned_text:
            return ParseResult(
                segments=[self._fallback_segment("", chapter_id, 0)],
                detected_characters=[],
            )

        try:
            prompt = self._build_prompt(cleaned_text)
            payload = {
                "model": self.model,
                "stream": False,
                "format": "json",
                "prompt": prompt,
            }
            self._append_llm_log(
                chapter_id=chapter_id,
                direction="request",
                payload={
                    "url": self.ollama_url,
                    "model": self.model,
                    "prompt": prompt,
                    "raw_text": source_text,
                    "cleaned_text": cleaned_text,
                },
            )
            response = requests.post(
                self.ollama_url,
                json=payload,
                timeout=self.timeout_s,
            )
            response.raise_for_status()
            response_json = response.json()
            llm_text = response_json.get("response", "")
            self._append_llm_log(
                chapter_id=chapter_id,
                direction="response",
                payload={
                    "response_json": response_json,
                    "response_text": llm_text,
                },
            )
            llm_data = self._parse_response_json(llm_text)
            return self._validate_result(llm_data, source_text=cleaned_text, chapter_id=chapter_id)
        except Exception as exc:
            self._append_llm_log(
                chapter_id=chapter_id,
                direction="error",
                payload={"error": str(exc)},
            )
            logger.warning("Dialogue parse failed; falling back to narration: %s", exc)
            return ParseResult(
                segments=[self._fallback_segment(cleaned_text, chapter_id, 0)],
                detected_characters=[],
            )

    @classmethod
    def _is_noise_line(cls, line: str) -> bool:
        text = (line or "").strip()
        if not text:
            return False
        lowered = text.lower()
        if lowered.startswith(("http://", "https://", "www.")):
            return True
        if re.fullmatch(r"[^\w]{3,}", lowered):
            return True
        for pattern in cls._UI_NOISE_PATTERNS:
            if re.search(pattern, lowered):
                return True
        return False

    @classmethod
    def _clean_text_for_llm(cls, text: str) -> str:
        source = (text or "").strip()
        if not source:
            return ""
        source_lines = [line.strip() for line in source.splitlines()]
        kept_lines = [line for line in source_lines if line and not cls._is_noise_line(line)]
        if not kept_lines:
            return source
        cleaned = "\n".join(kept_lines)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        if len(cleaned) < max(80, int(len(source) * 0.2)):
            return source
        return cleaned

    def _append_llm_log(self, *, chapter_id: str, direction: str, payload: dict) -> None:
        if not self.llm_log_path:
            return
        try:
            self.llm_log_path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "chapter_id": chapter_id,
                "direction": direction,
                "payload": payload,
            }
            with open(self.llm_log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            logger.debug("Failed writing LLM communication log.", exc_info=True)

    def _build_prompt(self, text: str) -> str:
        schema = {
            "segments": [
                {
                    "text": "string",
                    "type": "dialogue|thought|narration",
                    "speaker": "string",
                    "gender": "male|female|unknown",
                    "speaker_confidence": "float 0..1",
                    "gender_confidence": "float 0..1",
                    "character_confidence": "float 0..1",
                }
            ],
            "detected_characters": [
                {
                    "name": "string",
                    "gender": "male|female|unknown",
                    "confidence": "float 0..1",
                }
            ],
        }
        chapter_payload = json.dumps({"chapter_text": text}, ensure_ascii=False)
        return (
            "You are a chapter segmenter for TTS production.\n"
            "Return JSON only. No markdown or commentary.\n"
            "Segment the chapter in reading order.\n"
            "Identify text type (dialogue, thought, narration), speaker, speaker gender, and confidences.\n"
            "Use 'narrator' speaker for narration unless a clear character narrator exists.\n"
            "If uncertain, use gender='unknown' and low confidence values.\n"
            f"Expected JSON schema:\n{json.dumps(schema)}\n\n"
            "The chapter input is provided as JSON with one field named 'chapter_text'.\n"
            "Parse the value exactly as the chapter content.\n"
            f"CHAPTER INPUT JSON:\n{chapter_payload}"
        )

    @staticmethod
    def _parse_response_json(llm_text: str) -> dict:
        text = (llm_text or "").strip()
        if not text:
            raise ValueError("LLM returned empty response")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
            raise

    def _validate_result(self, data: dict, *, source_text: str, chapter_id: str) -> ParseResult:
        raw_segments = data.get("segments")
        if not isinstance(raw_segments, list) or not raw_segments:
            return ParseResult(
                segments=[self._fallback_segment(source_text, chapter_id, 0)],
                detected_characters=[],
            )

        segments: list[Segment] = []
        for idx, item in enumerate(raw_segments):
            segment = self._coerce_segment(item, chapter_id=chapter_id, index=idx)
            if segment and segment.text.strip():
                segments.append(segment)

        if not segments:
            segments = [self._fallback_segment(source_text, chapter_id, 0)]

        detected_characters = self._coerce_detected_characters(data.get("detected_characters"))
        return ParseResult(segments=segments, detected_characters=detected_characters)

    def _coerce_segment(self, item: object, *, chapter_id: str, index: int) -> Segment | None:
        if not isinstance(item, dict):
            return None
        text = str(item.get("text", "")).strip()
        if not text:
            return None

        seg_type = str(item.get("type", "narration")).strip().lower()
        if seg_type not in self._ALLOWED_TYPES:
            seg_type = "narration"

        speaker = str(item.get("speaker", "narrator")).strip() or "narrator"
        gender = str(item.get("gender", "unknown")).strip().lower()
        if gender not in self._ALLOWED_GENDERS:
            gender = "unknown"

        return Segment(
            text=text,
            type=seg_type,  # type: ignore[arg-type]
            speaker=speaker,
            gender=gender,  # type: ignore[arg-type]
            speaker_confidence=self._clamp_conf(item.get("speaker_confidence", 0.0)),
            gender_confidence=self._clamp_conf(item.get("gender_confidence", 0.0)),
            character_confidence=self._clamp_conf(item.get("character_confidence", 0.0)),
            paragraph_id=f"{chapter_id}_p{index}",
        )

    def _coerce_detected_characters(self, raw: object) -> list[DetectedCharacter]:
        if not isinstance(raw, list):
            return []
        result: list[DetectedCharacter] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            gender = str(item.get("gender", "unknown")).strip().lower()
            if gender not in self._ALLOWED_GENDERS:
                gender = "unknown"
            result.append(
                DetectedCharacter(
                    name=name,
                    gender=gender,  # type: ignore[arg-type]
                    confidence=self._clamp_conf(item.get("confidence", 0.0)),
                )
            )
        return result

    @staticmethod
    def _clamp_conf(value: object) -> float:
        try:
            num = float(value)
        except (TypeError, ValueError):
            num = 0.0
        return max(0.0, min(1.0, num))

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
