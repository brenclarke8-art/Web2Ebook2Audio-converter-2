from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Literal, Any, List
from urllib.parse import urlparse, urlunparse

from ebook_app.models.character_db import Character, normalize_character_name
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
        timeout_s: int = 300,
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

    def parse(
        self,
        text: str,
        chapter_id: str,
        manual_segment_hints: list[dict[str, str]] | None = None,
        story_context_block: str | None = None,
    ) -> DialogueParseResult:
        """
        MUST return:
          DialogueParseResult(
              segments=[Segment...],
              detected_characters=[DetectedCharacter...]
          )

        Args:
            text: Chapter text to parse.
            chapter_id: Stable identifier for this chapter (e.g. ``"ch001"``).
            story_context_block: Optional pre-formatted story-context string
                produced by ``StoryContext.to_prompt_block()``.  When provided,
                it is prepended to the user message sent to the LLM so the
                model can maintain continuity across chapters.
        """

        # LLM disabled → fallback
        if self.llm_mode == "off":
            clean = self.service.clean_text_for_llm(text)
            seg = self._fallback_segment(clean, chapter_id, 0)
            return DialogueParseResult(segments=[seg], detected_characters=[])

        # Call segmentation service
        try:
            parse_kwargs: dict = {
                "text": text,
                "chapter_id": chapter_id,
                "known_characters": self._known_characters_for_llm(),
            }
            if manual_segment_hints:
                parse_kwargs["manual_segment_hints"] = manual_segment_hints
            if story_context_block:
                parse_kwargs["story_context_block"] = story_context_block
            result = self.service.parse(**parse_kwargs)
        except Exception as exc:
            logger.error("DialogueSegmentationService.parse failed: %s", exc)
            clean = self.service.clean_text_for_llm(text)
            seg = self._fallback_segment(clean, chapter_id, 0)
            return DialogueParseResult(segments=[seg], detected_characters=[])

        raw_segments = getattr(result, "segments", []) or []
        raw_characters = getattr(result, "characters", []) or []

        # Warn when the LLM produced only a single narration fallback segment,
        # which indicates the model timed out or returned empty JSON.
        if (
            len(raw_segments) == 1
            and getattr(raw_segments[0], "type", None) == "narration"
            and getattr(raw_segments[0], "speaker", None) == "narrator"
        ):
            logger.warning(
                "Chapter %s: LLM returned a single fallback narration segment — "
                "the model may have timed out or failed to parse the text. "
                "Consider increasing 'dialogue_llm_timeout' or checking Ollama.",
                chapter_id,
            )

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
            speaker, db_gender = self._resolve_speaker(speaker)
            paragraph_id = self._make_paragraph_id(chapter_id, text_val, idx)

            gender, gender_conf = self._infer_gender_for_speaker(
                speaker=speaker,
                text=text_val,
                character_gender_map=gender_map,
            )
            if gender == "unknown" and db_gender in {"male", "female"}:
                gender = db_gender
                gender_conf = max(gender_conf, 0.95)

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
        seen_names: set[str] = set()

        for raw in raw_characters:
            name, gender, conf = self._normalize_character_entry(raw)
            if not name:
                continue

            resolved = self._resolve_character(name)
            if resolved:
                canonical, db_gender = resolved
                if normalize_character_name(canonical) != normalize_character_name(name):
                    self._merge_alias_into_db(canonical_name=canonical, alias=name)
                name = canonical
                if db_gender in {"male", "female"}:
                    gender = db_gender
                    conf = max(conf, 0.9)

            # Prefer gender from gender_map
            mapped = gender_map.get(name)
            if mapped and mapped != "unknown":
                gender = mapped
                conf = max(conf, 0.9)

            dedupe_key = normalize_character_name(name)
            if dedupe_key in seen_names:
                continue
            seen_names.add(dedupe_key)

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
    def _normalize_chat_url(url: str) -> str:
        cleaned = (url or "").strip()
        if not cleaned:
            return cleaned
        parsed = urlparse(cleaned)
        if parsed.path.endswith("/api/generate"):
            chat_path = parsed.path[: -len("/api/generate")] + "/api/chat"
            return urlunparse((parsed.scheme, parsed.netloc, chat_path, parsed.params, parsed.query, parsed.fragment))
        return cleaned

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
        normalized = " ".join(name.split()) or "narrator"
        if normalized.casefold() == "unknown":
            return "unknown"
        if normalized.casefold() == "narrator":
            return "narrator"
        return normalized

    def _build_character_gender_map(self, raw_characters: list[Any]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for raw in raw_characters:
            name, gender, _ = DialogueParser._normalize_character_entry(raw)
            if name and gender != "unknown":
                mapping[name] = gender
        for known in self._known_characters_for_llm():
            if not isinstance(known, dict):
                continue
            name = str(known.get("name", "")).strip()
            gender = str(known.get("gender", "")).strip().lower()
            if name and gender in {"male", "female"} and name not in mapping:
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
            resolved = self._resolve_character(name)
            existing = None
            if resolved:
                existing = self.character_db.get(resolved[0]) if hasattr(self.character_db, "get") else None
            elif hasattr(self.character_db, "get"):
                existing = self.character_db.get(name)

            if existing:
                if getattr(existing, "gender", "unknown") == "unknown" and gender in {"male", "female"}:
                    existing.gender = gender
                    if hasattr(self.character_db, "save"):
                        self.character_db.save()
                return

            if hasattr(self.character_db, "add"):
                self.character_db.add(Character(name=name, voice="", gender=gender))
            elif isinstance(self.character_db, list):
                target_norm = normalize_character_name(name)
                exists = any(
                    normalize_character_name(item.get("name", "")) == target_norm
                    for item in self.character_db
                    if isinstance(item, dict)
                )
                if not exists:
                    self.character_db.append({"name": name, "gender": gender, "confidence": confidence})
        except Exception as exc:
            logger.warning("Failed to merge character into DB: %s", exc)

    def _resolve_speaker(self, speaker: str) -> tuple[str, str]:
        if speaker in {"narrator", "unknown"}:
            return speaker, "unknown"
        resolved = self._resolve_character(speaker)
        if not resolved:
            return speaker, "unknown"
        canonical, gender = resolved
        return canonical, gender

    def _resolve_character(self, raw_name: str) -> tuple[str, str] | None:
        name = (raw_name or "").strip()
        if not name or not self.character_db:
            return None

        if hasattr(self.character_db, "resolve_name"):
            resolved = self.character_db.resolve_name(name)
            if resolved:
                return resolved.name, getattr(resolved, "gender", "unknown")

        if isinstance(self.character_db, list):
            norm = normalize_character_name(name)
            for item in self.character_db:
                if not isinstance(item, dict):
                    continue
                canonical = str(item.get("name", "")).strip()
                if not canonical:
                    continue
                if normalize_character_name(canonical) == norm:
                    return canonical, str(item.get("gender", "unknown")).strip().lower()
                aliases = item.get("aliases", [])
                if not isinstance(aliases, list):
                    aliases = []
                for alias in aliases:
                    if normalize_character_name(str(alias)) == norm:
                        return canonical, str(item.get("gender", "unknown")).strip().lower()
        return None

    def _merge_alias_into_db(self, canonical_name: str, alias: str) -> None:
        if not self.character_db or not canonical_name or not alias:
            return
        if hasattr(self.character_db, "merge_alias"):
            self.character_db.merge_alias(canonical_name, alias)
            return
        if isinstance(self.character_db, list):
            for item in self.character_db:
                if not isinstance(item, dict):
                    continue
                if normalize_character_name(str(item.get("name", ""))) != normalize_character_name(canonical_name):
                    continue
                aliases = item.get("aliases")
                if not isinstance(aliases, list):
                    aliases = []
                alias_clean = " ".join(alias.strip().split())
                alias_norm = normalize_character_name(alias_clean)
                if alias_clean and all(normalize_character_name(a) != alias_norm for a in aliases):
                    aliases.append(alias_clean)
                    item["aliases"] = aliases
                return

    def _known_characters_for_llm(self) -> list[dict[str, str | list[str]]]:
        if not self.character_db:
            return []

        if hasattr(self.character_db, "all"):
            out: list[dict[str, str | list[str]]] = []
            for char in self.character_db.all():
                out.append(
                    {
                        "name": getattr(char, "name", ""),
                        "aliases": list(getattr(char, "aliases", []) or []),
                        "gender": getattr(char, "gender", "unknown"),
                        "description": getattr(char, "description", ""),
                    }
                )
            return out

        if isinstance(self.character_db, list):
            out = []
            for item in self.character_db:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                aliases = item.get("aliases", [])
                alias_list: list[str] = []
                if isinstance(aliases, list):
                    for alias in aliases:
                        if not isinstance(alias, str):
                            continue
                        alias_clean = alias.strip()
                        if alias_clean:
                            alias_list.append(alias_clean)
                out.append(
                    {
                        "name": name,
                        "aliases": alias_list,
                        "gender": str(item.get("gender", "unknown")).strip().lower() or "unknown",
                        "description": str(item.get("description", "")).strip(),
                    }
                )
            return out

        return []
