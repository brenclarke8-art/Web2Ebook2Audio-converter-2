from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Literal, Any, List

from ebook_app.services.dialogue_segmentation_service import DialogueSegmentationService
from ebook_app.services.llm_client import OllamaChatClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes matching pipeline_contracts.py
# ---------------------------------------------------------------------------

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


@dataclass
class DetectedCharacter:
    name: str
    gender: Literal["male", "female", "unknown"] = "unknown"
    confidence: float = 0.0


@dataclass
class DialogueParseResult:
    segments: List[Segment]
    detected_characters: List[DetectedCharacter]


# Backward-compatible alias expected by older imports/tests.
ParseResult = DialogueParseResult


# ---------------------------------------------------------------------------
# Contract‑compliant DialogueParser
# ---------------------------------------------------------------------------

class DialogueParser:
    """
    Contract-compliant DialogueParser for Phase 5 of the pipeline.

    Fully compatible with:
      - DialogueParserContract
      - SegmentLike
      - DetectedCharacterLike
      - DialogueParseResult
    """

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
        character_db: Any | None = None,
        debug: bool = False,
    ) -> None:

        # Normalize URL to /api/chat
        self.ollama_url = self._normalize_chat_url(ollama_url or self._DEFAULT_OLLAMA_URL)

        self.model = (model or self._DEFAULT_MODEL).strip()
        self.timeout_s = int(timeout_s)
        self.retries = max(0, int(retries))
        self.llm_mode = (llm_mode or "full").strip().lower()
        self.llm_strict_quotes = bool(llm_strict_quotes)
        self.debug = bool(debug)
        self.character_db = character_db

        # LLM client + segmentation service
        self.client = OllamaChatClient(
            model=self.model,
            url=self.ollama_url,
            timeout_s=self.timeout_s,
            retries=self.retries,
            log_path=llm_log_path,
        )

        self.service = DialogueSegmentationService(
            client=self.client,
            strict_quotes=self.llm_strict_quotes,
        )

    # -----------------------------------------------------------------------
    # Public API (required by pipeline)
    # -----------------------------------------------------------------------

    def parse(self, text: str, chapter_id: str) -> DialogueParseResult:
        """
        MUST return:
          DialogueParseResult(
              segments=[Segment...],
              detected_characters=[DetectedCharacter...]
          )
        """

        # LLM disabled → fallback
        if self.llm_mode == "off":
            clean = self.service.clean_text_for_llm(text)
            seg = self._fallback_segment(clean, chapter_id, 0)
            return DialogueParseResult(segments=[seg], detected_characters=[])

        # Call segmentation service
        try:
            result = self.service.parse(text=text, chapter_id=chapter_id)
        except Exception as exc:
            logger.error("DialogueSegmentationService.parse failed: %s", exc)
            clean = self.service.clean_text_for_llm(text)
            seg = self._fallback_segment(clean, chapter_id, 0)
            return DialogueParseResult(segments=[seg], detected_characters=[])

        raw_segments = getattr(result, "segments", []) or []
        raw_characters = getattr(result, "characters", []) or []

        # Build gender map from LLM output
        gender_map = self._build_character_gender_map(raw_characters)

        # Convert raw segments → contract-compliant Segment objects
        segments = self._convert_segments(
            raw_segments=raw_segments,
            chapter_id=chapter_id,
            gender_map=gender_map,
        )

        # Convert raw characters → DetectedCharacter objects
        detected = self._convert_detected_characters(
            raw_characters=raw_characters,
            gender_map=gender_map,
        )

        return DialogueParseResult(
            segments=segments,
            detected_characters=detected,
        )

    # -----------------------------------------------------------------------
    # Segment conversion
    # -----------------------------------------------------------------------

    def _convert_segments(
        self,
        *,
        raw_segments: list[Any],
        chapter_id: str,
        gender_map: dict[str, str],
    ) -> List[Segment]:

        segments: List[Segment] = []

        for idx, item in enumerate(raw_segments):
            text_val = getattr(item, "text", "") or ""
            if not text_val.strip():
                continue

            seg_type = self._normalize_type(getattr(item, "type", "narration"))
            speaker = self._normalize_speaker_name(getattr(item, "speaker", "narrator"))
            paragraph_id = self._make_paragraph_id(chapter_id, text_val, idx)

            gender, gender_conf = self._infer_gender_for_speaker(
                speaker=speaker,
                text=text_val,
                character_gender_map=gender_map,
            )

            # Confidence defaults
            if speaker == "narrator":
                speaker_conf = 0.6
                char_conf = 1.0
            else:
                speaker_conf = 0.95
                char_conf = 0.95

            segments.append(
                Segment(
                    text=text_val,
                    type=seg_type,
                    speaker=speaker,
                    gender=gender,
                    speaker_confidence=speaker_conf,
                    gender_confidence=gender_conf,
                    character_confidence=char_conf,
                    paragraph_id=paragraph_id,
                )
            )

        # Fallback if LLM produced nothing
        if not segments:
            clean = self.service.clean_text_for_llm(text_val)
            return [self._fallback_segment(clean, chapter_id, 0)]

        return segments

    # -----------------------------------------------------------------------
    # Character conversion
    # -----------------------------------------------------------------------

    def _convert_detected_characters(
        self,
        *,
        raw_characters: list[Any],
        gender_map: dict[str, str],
    ) -> List[DetectedCharacter]:

        detected: List[DetectedCharacter] = []

        for raw in raw_characters:
            name, gender, conf = self._normalize_character_entry(raw)
            if not name:
                continue

            # Prefer gender from gender_map
            mapped = gender_map.get(name)
            if mapped and mapped != "unknown":
                gender = mapped
                conf = max(conf, 0.9)

            detected.append(
                DetectedCharacter(
                    name=name,
                    gender=gender,
                    confidence=conf,
                )
            )

            # Optional DB merge
            self._merge_character_into_db(name=name, gender=gender, confidence=conf)

        return detected

    # -----------------------------------------------------------------------
    # Helpers (unchanged from your implementation)
    # -----------------------------------------------------------------------

    @staticmethod
    def _fallback_segment(text: str, chapter_id: str, index: int) -> Segment:
        pid = DialogueParser._make_paragraph_id(chapter_id, text, index)
        return Segment(
            text=text,
            type="narration",
            speaker="narrator",
            gender="unknown",
            speaker_confidence=1.0,
            gender_confidence=0.0,
            character_confidence=1.0,
            paragraph_id=pid,
        )

    @staticmethod
    def _make_paragraph_id(chapter_id: str, text: str, index: int) -> str:
        prefix = (text or "")[:64]
        digest = hashlib.md5(prefix.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
        return f"{chapter_id}_{digest}_{index}"

    @staticmethod
    def _normalize_type(raw_type: str) -> Literal["dialogue", "thought", "narration"]:
        t = (raw_type or "").strip().lower()
        if t in {"dialogue", "dialog", "spoken", "speech"}:
            return "dialogue"
        if t in {"thought", "inner monologue", "monologue", "thinking", "mind"}:
            return "thought"
        return "narration"

    @staticmethod
    def _normalize_speaker_name(raw: str) -> str:
        if not raw:
            return "narrator"
        name = raw.strip()
        if "(" in name and name.endswith(")"):
            name = name[: name.rfind("(")].rstrip()
        while name and name[-1] in ".!?,":  # strip trailing punctuation
            name = name[:-1].rstrip()
        return " ".join(name.split()) or "narrator"

    @staticmethod
    def _build_character_gender_map(raw_characters: list[Any]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for raw in raw_characters:
            name, gender, _ = DialogueParser._normalize_character_entry(raw)
            if name and gender != "unknown":
                mapping[name] = gender
        return mapping

    @staticmethod
    def _normalize_character_entry(raw: Any) -> tuple[str, str, float]:
        name = None
        gender = "unknown"
        conf = 0.85

        if isinstance(raw, str):
            name = raw.strip()
        elif isinstance(raw, dict):
            name = (raw.get("name") or "").strip()
            g = (raw.get("gender") or "").strip().lower()
            if g in {"male", "female"}:
                gender = g
            if isinstance(raw.get("confidence"), (int, float)):
                conf = float(raw["confidence"])
        else:
            n = getattr(raw, "name", None)
            if isinstance(n, str):
                name = n.strip()
            g = getattr(raw, "gender", None)
            if isinstance(g, str) and g.lower() in {"male", "female"}:
                gender = g.lower()
            c = getattr(raw, "confidence", None)
            if isinstance(c, (int, float)):
                conf = float(c)

        if not name:
            return "", "unknown", 0.0

        return name, gender, conf

    @staticmethod
    def _infer_gender_for_speaker(
        speaker: str,
        text: str,
        character_gender_map: dict[str, str],
    ) -> tuple[str, float]:

        if speaker in character_gender_map:
            g = character_gender_map[speaker]
            if g != "unknown":
                return g, 0.95

        lower = (text or "").lower()
        male_hits = any(p in lower for p in [" he ", " his ", " him "])
        female_hits = any(p in lower for p in [" she ", " her "])

        if male_hits and not female_hits:
            return "male", 0.7
        if female_hits and not male_hits:
            return "female", 0.7

        return "unknown", 0.0

    def _merge_character_into_db(self, name: str, gender: str, confidence: float) -> None:
        if not self.character_db:
            return
        try:
            if hasattr(self.character_db, "get"):
                existing = self.character_db.get(name)
            else:
                existing = None

            if existing and hasattr(self.character_db, "update"):
                self.character_db.update(name=name, gender=gender, confidence=confidence)
            elif hasattr(self.character_db, "add"):
                self.character_db.add(name=name, gender=gender, confidence=confidence)

        except Exception as exc:
            logger.warning("Failed to merge character into DB (%s): %s", name, exc)
