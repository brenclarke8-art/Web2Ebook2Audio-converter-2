#!/usr/bin/env python3
"""
Dialogue Detection and Speaker Attribution

This module identifies dialogue/narration/thought segments and attributes speakers.
It uses regex for fast extraction and can optionally call Ollama for refinement.
"""

import re
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Literal, Union, Tuple
from dataclasses import dataclass
import requests
from pronoun_analyzer import PronounAnalyzer, CharacterProfile

logger = logging.getLogger(__name__)

SegmentType = Literal["dialogue", "narration", "thought"]

# LLM support level for the dialogue detector.
#   "off"  – regex-only extraction, no LLM calls at all.
#   "half" – regex extraction first, then per-segment LLM refinement (default
#             when use_llm=True for backward compatibility).
#   "full" – send the cleaned chapter to the LLM in one request and rely on it
#             to return structured JSON with characters, speakers, and segment
#             types for the multi-speaker pipeline.
#   "db_only" – regex path, but only treat segments as dialogue when the speaker
#               is in known_characters (typically DB/user-provided); everything
#               else is narration.
LLMMode = Literal["off", "half", "full", "db_only"]

_SEGMENTATION_SYSTEM_PROMPT = (
    "You are a deterministic JSON segmentation engine for scraped fiction.\n"
    "Convert the cleaned input text into strict JSON for a multi-speaker TTS pipeline.\n"
    "\n"
    "Return a JSON object with exactly these top-level keys:\n"
    '{\n'
    '  "characters": ["Name1", "Name2"],\n'
    '  "segments": [\n'
    '    {"text": "<exact text>", "type": "dialogue"|"thought"|"general", "speaker": "<character>"|"narrator"|null}\n'
    "  ]\n"
    "}\n"
    "\n"
    "Rules:\n"
    "1. Preserve the original reading order.\n"
    "2. Segment the full text into sequential chunks without dropping story text.\n"
    "3. Use type=dialogue for spoken text, type=thought for internal monologue, and type=general for everything else.\n"
    "4. Use provided characters as authoritative hints, but you may add clearly text-backed new characters.\n"
    "5. For narration/general text, speaker should be narrator or null.\n"
    "6. Do not invent characters that are not supported by the text.\n"
    "7. Return only strict JSON with no markdown, prose, or comments."
)

_JSON_REPAIR_SYSTEM_PROMPT = (
    "You are a JSON repair engine.\n"
    "Fix the JSON so it is valid and parseable.\n"
    "Do NOT add commentary.\n"
    "Return ONLY valid JSON."
)


@dataclass
class DialogueSegment:
    """Represents a segment of text and optional speaker attribution."""

    text: str
    speaker: Optional[str] = None  # Character name or 'narrator'
    type: SegmentType = "narration"
    start_pos: int = 0
    end_pos: int = 0
    confidence: float = 1.0  # Detection confidence 0.0 – 1.0

    @property
    def is_dialogue(self) -> bool:
        # Treat thought as dialogue-like for voice assignment and previews.
        return self.type in ("dialogue", "thought")


class OllamaClient:
    """Minimal client for local Ollama chat endpoint with JSON responses."""

    def __init__(
        self,
        model: str = "mistral:instruct",
        url: str = "http://localhost:11434/api/chat",
        timeout: int = 20,
        log_path: Optional[str] = None,
    ):
        self.model = model
        self.url = url
        self.timeout = timeout
        self.disabled = False
        self.log_path = log_path
        if log_path:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    def ask_json(self, system: str, user: Union[str, Dict]) -> Dict:
        """Send a chat request and parse a JSON object from response content.

        Args:
            system: System prompt text.
            user: User message – either a plain string (sent verbatim) or a dict
                  (serialised as JSON before sending).
        """
        if self.disabled:
            return {}

        user_content = user if isinstance(user, str) else json.dumps(user)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
        }

        try:
            start_time = time.perf_counter()
            logger.debug(
                "LLM request -> model=%s url=%s timeout=%ss system=%s user=%s",
                self.model,
                self.url,
                self.timeout,
                self._preview_text(system),
                self._preview_text(json.dumps(user)),
            )
            resp = requests.post(self.url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "")
            elapsed = time.perf_counter() - start_time
            parsed = self._parse_json_content(content)
            if not parsed and content:
                parsed = self._repair_json_content(content)
            logger.debug(
                "LLM response <- status=%s elapsed=%.2fs raw=%s parsed=%s",
                resp.status_code,
                elapsed,
                self._preview_text(content),
                self._preview_text(json.dumps(parsed)),
            )
            self._write_log_entry(
                request=payload,
                response_status=resp.status_code,
                response_raw=content,
                response_parsed=parsed,
                elapsed=elapsed,
            )
            return parsed
        except Exception as exc:
            # Disable after first hard failure to avoid repeated slow retries.
            self.disabled = True
            logger.warning(f"Ollama unavailable or invalid response; disabling LLM refinement: {exc}")
            self._write_log_entry(
                request=payload,
                error=str(exc),
            )
            return {}

    def _write_log_entry(
        self,
        request: Dict,
        response_status: Optional[int] = None,
        response_raw: Optional[str] = None,
        response_parsed: Optional[Dict] = None,
        elapsed: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """Append a single JSON-lines record to the LLM communication log."""
        if not self.log_path:
            return
        record: Dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": self.model,
            "url": self.url,
            "request": request,
        }
        if error is not None:
            record["error"] = error
        else:
            record["response_status"] = response_status
            record["elapsed_seconds"] = None if elapsed is None else round(elapsed, 3)
            record["response_raw"] = response_raw
            record["response_parsed"] = response_parsed
        try:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Could not write LLM log entry: %s", exc)

    @staticmethod
    def _preview_text(text: str, limit: int = 500) -> str:
        """Trim log payloads to keep debug output readable."""
        if text is None:
            return ""
        compact = " ".join(str(text).split())
        if len(compact) <= limit:
            return compact
        return f"{compact[:limit]}... [truncated {len(compact) - limit} chars]"

    def _parse_json_content(self, content: str) -> Dict:
        if not content:
            return {}

        # Try raw JSON first.
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Fallback: extract first JSON object from mixed text or fenced output.
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match:
            return {}

        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _repair_json_content(self, content: str) -> Dict:
        """Attempt one repair round-trip when model output is malformed JSON."""
        repair_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _JSON_REPAIR_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "stream": False,
        }
        try:
            resp = requests.post(self.url, json=repair_payload, timeout=self.timeout)
            resp.raise_for_status()
            repaired_content = resp.json().get("message", {}).get("content", "")
            repaired = self._parse_json_content(repaired_content)
            if repaired:
                logger.debug("LLM JSON repair succeeded")
            else:
                logger.debug("LLM JSON repair returned no parseable object")
            return repaired
        except Exception as exc:
            logger.debug("LLM JSON repair failed: %s", exc)
            return {}


class DialogueDetector:
    """Detects dialogue in text and attributes it to speakers."""

    # Common dialogue tags that indicate speech
    SPEECH_VERBS = {
        'said', 'asked', 'replied', 'answered', 'shouted', 'whispered', 'muttered',
        'yelled', 'screamed', 'cried', 'exclaimed', 'explained', 'continued',
        'added', 'remarked', 'stated', 'declared', 'announced', 'suggested',
        'mentioned', 'noted', 'observed', 'commented', 'responded', 'retorted',
        'insisted', 'argued', 'protested', 'agreed', 'admitted', 'confessed',
        'wondered', 'thought', 'mused', 'pondered', 'questioned', 'demanded',
        'ordered', 'commanded', 'instructed', 'warned', 'advised', 'urged',
        'pleaded', 'begged', 'called', 'greeted', 'thanked', 'apologized',
        'sighed', 'laughed', 'chuckled', 'giggled', 'snorted', 'groaned',
        'murmured', 'stammered', 'stuttered', 'breathed', 'hissed', 'growled'
    }

    NAME_PATTERN = r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*'

    # Quote content patterns: allow single line-wraps inside a quote but stop
    # at paragraph breaks (consecutive newlines), preventing runaway matches.
    _DQUOTE_CONTENT = r'(?:[^"\n]|\n(?!\n))+'
    _SQUOTE_CONTENT = r"(?:[^'\n]|\n(?!\n))+"

    # Patterns for detecting dialogue
    # 'after' patterns (Speaker said, "Text") must come before 'before' patterns
    # ("Text," speaker said) so that attributed speech is matched first and
    # prevents the 'before' greedy match from consuming cross-sentence whitespace.
    DIALOGUE_PATTERNS = [
        # Speaker said, "Text" (multi-line)
        (r'(' + NAME_PATTERN + r')\s+(' + '|'.join(SPEECH_VERBS) + r')[,:]?\s+"(' + _DQUOTE_CONTENT + r')"', 'after'),
        # Speaker said, 'Text' (multi-line)
        (r"(" + NAME_PATTERN + r")\s+(" + '|'.join(SPEECH_VERBS) + r")[,:]?\s+'(" + _SQUOTE_CONTENT + r")'", 'after'),
        # "Text," speaker said (multi-line)
        (r'"(' + _DQUOTE_CONTENT + r')"[,\s]+(' + NAME_PATTERN + r')\s+(' + '|'.join(SPEECH_VERBS) + r')', 'before'),
        # 'Text,' speaker said (multi-line)
        (r"'(" + _SQUOTE_CONTENT + r")'[,\s]+(" + NAME_PATTERN + r")\s+(" + '|'.join(SPEECH_VERBS) + r')', 'before'),
        # "Text" (multi-line)
        (r'"(' + _DQUOTE_CONTENT + r')"', 'none'),
        # 'Text' (multi-line)
        (r"'(" + _SQUOTE_CONTENT + r")'", 'none'),
    ]

    # Confidence constants for scoring detected and LLM-refined segments.
    _CONF_KNOWN_SPEAKER = 0.9      # Attributed to a known character via regex
    _CONF_INFERRED_SPEAKER = 0.65  # Speaker resolved from surrounding context
    _CONF_UNATTRIBUTED = 0.5       # Quoted text with no speaker information
    _CONF_LLM_FALLBACK = 0.7       # LLM-parsed segment (broken quote fallback)
    _CONF_LLM_SPEAKER_MIN = 0.7    # Minimum confidence after LLM speaker update
    _CONF_LLM_RECLASSIFY_BONUS = 0.1  # Confidence boost when LLM changes type
    _MAX_UI_LINE_WORDS = 7
    _WORD_RE = re.compile(r"[A-Za-z0-9']+")
    _CHAPTER_RE = re.compile(r"\bchapter\s+\d+\b")
    _SENTENCE_END_RE = re.compile(r"[.!?…]$")
    _UI_LINE_CONTAINS = (
        "sign in",
        "sign up",
        "forum",
        "theme",
        "tools",
        "navigation",
        "reader mode",
        "back to novel",
        "next",
        "previous",
        "fucknovelpia",
    )

    def __init__(
        self,
        pronoun_analyzer: Optional[PronounAnalyzer] = None,
        use_llm: bool = False,
        llm_mode: Optional[LLMMode] = None,
        llm_client: Optional[OllamaClient] = None,
        llm_model: str = "mistral:instruct",
        llm_url: str = "http://localhost:11434/api/chat",
        llm_timeout: int = 200,
        llm_log_path: Optional[str] = None,
        llm_strict_quotes: bool = False,
    ):
        """Initialize DialogueDetector

        Args:
            pronoun_analyzer: Optional PronounAnalyzer instance for character extraction
            use_llm: Backward-compatible flag; True maps to llm_mode="half".
                     Ignored when llm_mode is explicitly set.
            llm_mode: LLM support level: "off" (regex only), "half" (regex + LLM
                      refinement), or "full" (entire chapter sent to LLM at once).
                      Overrides use_llm when provided.
            llm_client: Optional custom Ollama client
            llm_model: Ollama model name
            llm_url: Ollama chat API URL
            llm_timeout: Timeout per LLM request in seconds
            llm_log_path: Optional path to a JSON-lines file where every LLM
                          request and response will be recorded in full.
            llm_strict_quotes: When True, LLM outputs are constrained so only
                              text written in double quotes is treated as
                              dialogue; all other text is forced to narration.
        """
        logger.debug("Initializing DialogueDetector")
        self.pronoun_analyzer = pronoun_analyzer or PronounAnalyzer()

        if llm_mode is not None:
            self.llm_mode: LLMMode = llm_mode
        else:
            self.llm_mode = "half" if use_llm else "off"

        # use_llm stays True only for modes that actually call the LLM.
        self.use_llm = self.llm_mode in ("half", "full")

        self.llm = llm_client or OllamaClient(
            model=llm_model,
            url=llm_url,
            timeout=llm_timeout,
            log_path=llm_log_path,
        )
        self.llm_strict_quotes = bool(llm_strict_quotes)
        self.characters = {}  # Will be populated during analysis
        self._last_segments: List[DialogueSegment] = []
        self._last_mode_path: List[str] = [self.llm_mode]
        logger.debug(
            "DialogueDetector initialized: llm_mode=%s strict_quotes=%s",
            self.llm_mode,
            self.llm_strict_quotes,
        )

    def detect_dialogue_in_text(
        self,
        text: str,
        known_characters: Optional[List[str]] = None,
        known_character_records: Optional[List[Dict]] = None,
    ) -> List[DialogueSegment]:
        """Detect all dialogue segments in text and attribute to speakers.

        Behaviour depends on llm_mode:
          "off"  – regex extraction only; no LLM calls.
          "half" – regex extraction then per-segment LLM refinement.
          "full" – send cleaned chapter text to the LLM and use its structured
                    JSON response as the ground truth for segments/characters.
          "db_only" – regex extraction only, but only DB/user-known speakers are
                      treated as dialogue; all other segments become narration.

        Args:
            text: Text to analyze
            known_characters: Optional list of known character names
            known_character_records: Optional list of full character records from the
                character database (used as the validation corpus in "full" mode).

        Returns:
            List of DialogueSegment objects with speaker attribution
        """
        logger.info(
            "Starting dialogue detection on %d characters of text (mode=%s)",
            len(text), self.llm_mode,
        )
        self._last_mode_path = [self.llm_mode]

        if self.llm_mode == "full":
            segments = self._analyze_full_chapter_with_llm(
                text, known_characters, known_character_records
            )
            dialogue_count = sum(1 for s in segments if s.is_dialogue)
            logger.info(
                "Full-LLM mode: %d total segments (%d dialogue/thought, %d narration)",
                len(segments), dialogue_count, len(segments) - dialogue_count,
            )
            self._last_segments = segments
            return segments

        segments = self._detect_regex_mode(
            text,
            known_characters=known_characters,
            mode=self.llm_mode,
        )
        dialogue_count = sum(1 for s in segments if s.is_dialogue)
        logger.info(
            f"Found {len(segments)} total segments ({dialogue_count} dialogue/thought, {len(segments) - dialogue_count} narration)"
        )
        self._last_segments = segments

        return segments

    def _detect_regex_mode(
        self,
        text: str,
        known_characters: Optional[List[str]],
        mode: LLMMode,
    ) -> List[DialogueSegment]:
        # "off" and "half" both start with regex + pronoun analysis.
        # "db_only" skips extraction and only uses user/DB-provided characters.
        if mode == "db_only":
            self.characters = {}
            for name in known_characters or []:
                if isinstance(name, str):
                    clean = name.strip()
                    if clean and not self._is_narrator_name(clean):
                        self.characters[clean] = CharacterProfile(name=clean)
            logger.info(
                "DB-only mode: loaded %d known character(s) from input",
                len(self.characters),
            )
        elif known_characters:
            logger.debug(f"Using {len(known_characters)} known characters")
            self.pronoun_analyzer.analyze_text(text, known_characters=known_characters)
            self.characters = self.pronoun_analyzer.characters
        else:
            logger.debug("Extracting characters from text")
            self.pronoun_analyzer.analyze_text(text)
            self.characters = self.pronoun_analyzer.characters
        logger.info("Detected %d characters", len(self.characters))

        if mode == "half" and not known_characters and self.characters and not self._is_llm_disabled():
            candidates = list(self.characters.keys())
            validated = self._validate_characters_with_llm(candidates)
            for name in list(self.characters.keys()):
                if name not in validated:
                    logger.debug("Dropping unvalidated character candidate: '%s'", name)
                    del self.characters[name]
            logger.info("Characters after LLM validation: %d", len(self.characters))

        allow_inference = mode != "db_only"
        segments = self._extract_dialogue_segments(text, allow_inference=allow_inference)
        if mode == "half":
            segments = self._refine_with_llm(text, segments)
        elif mode == "db_only":
            segments = self._enforce_known_speakers_only(segments)
        return segments

    def get_last_mode_path(self) -> List[str]:
        return list(self._last_mode_path)

    def _is_llm_disabled(self) -> bool:
        return bool(getattr(self.llm, "disabled", False))

    def _enforce_known_speakers_only(self, segments: List[DialogueSegment]) -> List[DialogueSegment]:
        """In DB-only mode, only known speakers remain dialogue; all else is narration."""
        known_lookup = {name.casefold() for name in self.characters.keys()}
        for segment in segments:
            if segment.type not in ("dialogue", "thought"):
                continue
            speaker = segment.speaker
            if not isinstance(speaker, str) or speaker.casefold() not in known_lookup:
                segment.type = "narration"
                segment.speaker = "narrator"
                segment.confidence = 1.0
        return segments

    def _analyze_full_chapter_with_llm(
        self,
        text: str,
        known_characters: Optional[List[str]] = None,
        known_character_records: Optional[List[Dict]] = None,
    ) -> List[DialogueSegment]:
        """Single-pass LLM pipeline for chapter-level segmentation.

        The cleaned chapter text is sent to the LLM once. The returned JSON is
        used directly for the character checklist/database and for multi-speaker
        voice switching.

        Args:
            text: Full chapter text to analyse.
            known_characters: Optional list of known character name strings.
            known_character_records: Optional list of full character records
                from the character database, used as authoritative name hints.

        Returns:
            List of DialogueSegment objects built from the structured LLM output.
        """
        logger.info("Full-LLM mode: requesting structured segmentation (%d chars)", len(text))

        authoritative_characters = self._collect_authoritative_characters(
            known_characters, known_character_records
        )
        llm_text = self._preprocess_full_mode_text(text)
        new_character_candidates = self._collect_new_character_candidates(
            llm_text,
            authoritative_characters,
        )
        pass1_payload = {
            "text": llm_text,
            "characters": authoritative_characters,
            "new_character_candidates": new_character_candidates,
        }

        structured = self.llm.ask_json(
            system=_SEGMENTATION_SYSTEM_PROMPT,
            user=pass1_payload,
        )
        structured = self._normalize_full_mode_payload(
            structured,
            authoritative_characters=authoritative_characters,
            allowed_new_characters=new_character_candidates,
        )

        raw_segments = structured.get("segments")
        raw_characters = structured.get("characters") or []

        if not isinstance(raw_segments, list) or not raw_segments:
            logger.warning(
                "Full-LLM mode: no usable structured segments returned; using narration fallback"
            )
            self._sync_character_profiles_from_llm(llm_text, authoritative_characters)
            return self._build_narration_fallback_segments(llm_text)

        logger.info("Full-LLM mode: structured output has %d segment(s)", len(raw_segments))

        character_names = self._merge_character_names(raw_characters, raw_segments)
        self._sync_character_profiles_from_llm(llm_text, character_names)
        character_names = list(self.characters.keys())
        segments: List[DialogueSegment] = []
        offset = 0

        for item in raw_segments:
            if not isinstance(item, dict):
                continue

            item_text = item.get("text", "")
            if not item_text:
                continue

            item_type = item.get("type", "narration")
            if item_type not in ("dialogue", "narration", "thought"):
                item_type = "narration"

            item_speaker = self._normalize_speaker_name(item.get("speaker"), character_names)
            if item_type == "narration" and not item_speaker:
                item_speaker = "narrator"

            segments.append(
                DialogueSegment(
                    text=item_text,
                    speaker=item_speaker,
                    type=item_type,
                    start_pos=offset,
                    end_pos=offset + len(item_text),
                    confidence=self._CONF_LLM_FALLBACK,
                )
            )
            offset += len(item_text)

        if not segments:
            logger.warning("Full-LLM mode: segment list empty after parsing; using narration fallback")
            return self._build_narration_fallback_segments(llm_text)

        logger.debug(
            "Full-LLM mode: built %d segment(s) from ground-truth output", len(segments)
        )
        return segments

    def _build_narration_fallback_segments(self, text: str) -> List[DialogueSegment]:
        clean = (text or "").strip()
        if not clean:
            return []
        return [
            DialogueSegment(
                text=clean,
                speaker="narrator",
                type="narration",
                start_pos=0,
                end_pos=len(clean),
                confidence=1.0,
            )
        ]

    def _merge_character_names(
        self,
        raw_characters: Optional[List[str]],
        raw_segments: Optional[List[Dict]],
    ) -> List[str]:
        names: List[str] = []
        seen = set()

        def add_name(value: Optional[str]) -> None:
            if not isinstance(value, str):
                return
            clean = value.strip()
            if not clean or self._is_narrator_name(clean):
                return
            key = clean.casefold()
            if key in seen:
                return
            seen.add(key)
            names.append(clean)

        for name in raw_characters or []:
            add_name(name)
        for item in raw_segments or []:
            if isinstance(item, dict):
                add_name(item.get("speaker"))
        return names

    def _sync_character_profiles_from_llm(self, text: str, character_names: Optional[List[str]]) -> None:
        ordered_names = [
            name.strip()
            for name in (character_names or [])
            if isinstance(name, str) and name.strip() and not self._is_narrator_name(name)
        ]
        if ordered_names:
            self.pronoun_analyzer.analyze_text(text, known_characters=ordered_names)
            analyzed = dict(self.pronoun_analyzer.characters)
        else:
            analyzed = {}

        self.characters = {}
        for name in ordered_names:
            profile = analyzed.get(name) or CharacterProfile(name=name)
            if profile.mention_count == 0:
                profile.mention_count = len(
                    re.findall(r'\b' + re.escape(name) + r'\b', text, flags=re.IGNORECASE)
                )
            self.characters[name] = profile

    def _collect_authoritative_characters(
        self,
        known_characters: Optional[List[str]],
        known_character_records: Optional[List[Dict]],
    ) -> List[str]:
        names: List[str] = []
        seen = set()

        for name in known_characters or []:
            if isinstance(name, str):
                clean = name.strip()
                if clean and clean.casefold() not in seen and not self._is_narrator_name(clean):
                    seen.add(clean.casefold())
                    names.append(clean)

        for record in known_character_records or []:
            if not isinstance(record, dict):
                continue
            record_name = record.get("name")
            if isinstance(record_name, str):
                clean = record_name.strip()
                if clean and clean.casefold() not in seen and not self._is_narrator_name(clean):
                    seen.add(clean.casefold())
                    names.append(clean)

        return names

    def _collect_new_character_candidates(
        self,
        text: str,
        authoritative_characters: Optional[List[str]] = None,
    ) -> List[str]:
        authoritative_lookup = {
            name.casefold(): name
            for name in (authoritative_characters or [])
            if isinstance(name, str) and name.strip()
        }
        extracted = self.pronoun_analyzer.extract_characters_from_text(text)
        candidates = [
            name for name in extracted
            if isinstance(name, str)
            and name.strip()
            and name.casefold() not in authoritative_lookup
            and not self._is_narrator_name(name)
        ]
        if not candidates:
            return []

        deduped: List[str] = []
        seen = set()
        for name in candidates:
            clean = name.strip()
            key = clean.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(clean)
        return deduped

    def _word_tokens(self, text: str) -> List[str]:
        return self._WORD_RE.findall(text)

    @staticmethod
    def _is_narrator_name(name: str) -> bool:
        return isinstance(name, str) and name.strip().casefold() == "narrator"

    @staticmethod
    def _is_fully_double_quoted(text: str) -> bool:
        clean = (text or "").strip()
        if len(clean) < 2:
            return False
        return (
            (clean.startswith('"') and clean.endswith('"'))
            or (clean.startswith("“") and clean.endswith("”"))
        )

    @staticmethod
    def _extract_double_quoted_chunks(text: str) -> List[str]:
        # Extract content inside double quotes while permitting wrapped lines.
        # Newlines are allowed only when not followed by another newline.
        pattern = r'"([^"\n]*(?:\n(?!\n)[^"\n]*)*)"|“([^”\n]*(?:\n(?!\n)[^”\n]*)*)”'
        matches = re.finditer(pattern, text or "")
        chunks: List[str] = []
        for match in matches:
            chunk = (match.group(1) or match.group(2) or "").strip()
            if chunk:
                chunks.append(chunk)
        return chunks

    def _is_strict_dialogue_candidate(self, text: str, source_text: Optional[str] = None) -> bool:
        clean = (text or "").strip()
        if not clean:
            return False

        for chunk in self._extract_double_quoted_chunks(source_text or ""):
            # `clean` may be either the bare chunk (`Hello`) or include quotes
            # (`"Hello"`) depending on which pipeline produced the segment text.
            if clean == chunk or clean == f'"{chunk}"':
                return True

        if self._is_fully_double_quoted(clean):
            return bool(clean[1:-1].strip())

        # Be flexible with LLM segmentation: keep dialogue classifications when
        # the segment includes quoted speech plus attribution context.
        return bool(self._extract_double_quoted_chunks(clean))

    def _apply_strict_quote_rule(
        self,
        text: str,
        seg_type: str,
        seg_speaker: Optional[str],
        source_text: Optional[str] = None,
    ) -> Tuple[str, Optional[str]]:
        if not self.llm_strict_quotes:
            return seg_type, seg_speaker
        if self._is_strict_dialogue_candidate(text, source_text=source_text):
            return "dialogue", seg_speaker
        return "narration", None

    def _is_obvious_ui_line(self, line: str, words: Optional[List[str]] = None) -> bool:
        clean = line.strip()
        if not clean:
            return True
        words = words if words is not None else self._word_tokens(clean)

        lowered = clean.lower()
        if any(token in lowered for token in self._UI_LINE_CONTAINS):
            return True
        if "←" in clean or "→" in clean:
            return True
        if self._CHAPTER_RE.search(lowered):
            return True

        has_alpha = any(char.isalpha() for char in clean)
        if has_alpha and len(words) <= self._MAX_UI_LINE_WORDS and clean == clean.upper():
            return True

        return False

    def _looks_like_story_line(self, line: str) -> bool:
        clean = line.strip()
        if not clean:
            return False
        words = self._word_tokens(clean)
        if self._is_obvious_ui_line(clean, words):
            return False
        if '"' in clean or "'" in clean:
            return True
        if self._SENTENCE_END_RE.search(clean):
            return True
        return len(words) >= 6

    def preprocess_story_text(self, text: str) -> str:
        """Strip obvious UI/boilerplate lines before downstream processing."""
        return self._preprocess_full_mode_text(text)

    def _preprocess_full_mode_text(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines()]
        filtered = [line for line in lines if line and not self._is_obvious_ui_line(line)]

        deduped: List[str] = []
        for line in filtered:
            if deduped and deduped[-1] == line:
                continue
            deduped.append(line)

        first_story_idx = 0
        for idx, line in enumerate(deduped):
            if self._looks_like_story_line(line):
                first_story_idx = idx
                break

        candidate = deduped[first_story_idx:] if deduped else []
        cleaned = "\n".join(candidate).strip()
        return cleaned or text

    def _extract_character_names_from_segments(self, segments: List[Dict]) -> List[str]:
        names: List[str] = []
        seen = set()

        def add_name(value: str) -> None:
            clean = value.strip()
            if not clean or self._is_narrator_name(clean):
                return
            if clean.casefold() in seen:
                return
            seen.add(clean.casefold())
            names.append(clean)

        for item in segments:
            if not isinstance(item, dict):
                continue

            speaker = item.get("speaker")
            if isinstance(speaker, str):
                add_name(speaker)

            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                continue

            for extracted in self.pronoun_analyzer.extract_characters_from_text(text):
                if isinstance(extracted, str):
                    add_name(extracted)

        return names

    def _normalize_full_mode_payload(
        self,
        payload: Dict,
        authoritative_characters: Optional[List[str]] = None,
        allowed_new_characters: Optional[List[str]] = None,
    ) -> Dict:
        if not isinstance(payload, dict):
            payload = {}

        authoritative_characters = authoritative_characters or []
        authoritative_lookup = {name.casefold(): name for name in authoritative_characters}
        allowed_new_lookup = {
            name.casefold(): name
            for name in (allowed_new_characters or [])
            if isinstance(name, str) and name.strip() and not self._is_narrator_name(name)
        }
        accepted_new_lookup: Dict[str, str] = {}

        raw_segments = payload.get("segments")
        normalized_segments: List[Dict] = []
        if isinstance(raw_segments, list):
            for item in raw_segments:
                if not isinstance(item, dict):
                    continue

                raw_text = item.get("text")
                if not isinstance(raw_text, str):
                    raw_text = str(raw_text or "")
                seg_text = raw_text.strip()
                if not seg_text:
                    continue

                seg_type = item.get("type")
                if seg_type == "general":
                    seg_type = "narration"
                if seg_type not in ("dialogue", "narration", "thought"):
                    if seg_text.startswith('"') and seg_text.endswith('"'):
                        seg_type = "dialogue"
                    elif seg_text.startswith("'") and seg_text.endswith("'"):
                        seg_type = "thought"
                    else:
                        seg_type = "narration"

                seg_speaker = None
                raw_speaker = item.get("speaker")
                if seg_type != "narration" and isinstance(raw_speaker, str):
                    clean_speaker = raw_speaker.strip()
                    if clean_speaker:
                        if authoritative_lookup:
                            speaker_key = clean_speaker.casefold()
                            seg_speaker = authoritative_lookup.get(speaker_key)
                            if not seg_speaker and speaker_key in allowed_new_lookup:
                                seg_speaker = allowed_new_lookup[speaker_key]
                                accepted_new_lookup[speaker_key] = seg_speaker
                        elif not self._is_narrator_name(clean_speaker):
                            seg_speaker = clean_speaker

                seg_type, seg_speaker = self._apply_strict_quote_rule(
                    seg_text, seg_type, seg_speaker
                )
                normalized_segments.append(
                    {"text": seg_text, "type": seg_type, "speaker": seg_speaker}
                )

        raw_characters = payload.get("characters")
        extracted_characters: List[str] = []
        if isinstance(raw_characters, list):
            for name in raw_characters:
                if isinstance(name, str):
                    clean = name.strip()
                    if not clean or self._is_narrator_name(clean):
                        continue
                    key = clean.casefold()
                    if authoritative_lookup:
                        if key in authoritative_lookup:
                            extracted_characters.append(authoritative_lookup[key])
                        elif key in allowed_new_lookup:
                            canonical = allowed_new_lookup[key]
                            extracted_characters.append(canonical)
                            accepted_new_lookup[key] = canonical
                    else:
                        extracted_characters.append(clean)

        if not extracted_characters and not authoritative_lookup:
            extracted_characters = self._extract_character_names_from_segments(normalized_segments)

        final_characters: List[str] = []
        seen = set()
        if authoritative_characters:
            source_chars = list(authoritative_characters)
            for name in extracted_characters:
                key = name.casefold()
                canonical = authoritative_lookup.get(key) or allowed_new_lookup.get(key)
                if canonical:
                    source_chars.append(canonical)
            source_chars.extend(accepted_new_lookup.values())
        else:
            source_chars = extracted_characters
        for name in source_chars:
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            final_characters.append(name)

        # Re-normalize speakers against final character list when we do not have
        # authoritative names from DB/known input.
        if not authoritative_lookup and final_characters:
            final_lookup = {name.casefold(): name for name in final_characters}
            for seg in normalized_segments:
                speaker = seg.get("speaker")
                if isinstance(speaker, str):
                    seg["speaker"] = final_lookup.get(speaker.casefold())

        return {"characters": final_characters, "segments": normalized_segments}

    def _extract_dialogue_segments(self, text: str, allow_inference: bool = True) -> List[DialogueSegment]:
        """Extract dialogue and narration segments from text"""
        segments = []
        used_ranges: List[tuple] = []
        character_names = list(self.characters.keys())

        # Find all dialogue with attribution
        dialogue_matches = []

        for pattern, speaker_position in self.DIALOGUE_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                start = match.start()
                end = match.end()

                if self._overlaps_existing(start, end, used_ranges):
                    continue

                # Determine dialogue text and speaker based on pattern type
                if speaker_position == 'before':
                    # "Text," Speaker said
                    dialogue_text = match.group(1)
                    speaker_name = match.group(2)
                elif speaker_position == 'after':
                    # Speaker said, "Text"
                    speaker_name = match.group(1)
                    dialogue_text = match.group(3)
                else:
                    # Just quoted text, no clear speaker
                    dialogue_text = match.group(1)
                    speaker_name = None

                if speaker_name:
                    normalized_speaker = self._normalize_speaker_name(
                        speaker_name, character_names
                    )
                    if normalized_speaker:
                        speaker_name = normalized_speaker

                is_known = speaker_name in self.characters if speaker_name else False

                # Validate speaker is a known character
                if allow_inference and speaker_name and not is_known:
                    # Try to infer from nearby context
                    inferred = self._infer_speaker_from_context(text, start, end)
                    logger.debug(
                        "Speaker '%s' not in known characters; inferred '%s' from context",
                        speaker_name, inferred,
                    )
                    speaker_name = inferred
                    is_known = speaker_name in self.characters if speaker_name else False

                confidence = self._calculate_segment_confidence(
                    speaker=speaker_name,
                    speaker_position=speaker_position,
                    is_known_character=is_known,
                )
                logger.debug(
                    "Matched dialogue at %d-%d: speaker=%s position=%s confidence=%.2f text=%.40r",
                    start, end, speaker_name, speaker_position, confidence, dialogue_text,
                )

                dialogue_matches.append({
                    'text': dialogue_text,
                    'speaker': speaker_name,
                    'start': start,
                    'end': end,
                    'is_dialogue': True,
                    'confidence': confidence,
                })
                used_ranges.append((start, end))

        # Sort by position
        dialogue_matches.sort(key=lambda x: x['start'])

        logger.debug("Found %d dialogue matches via regex", len(dialogue_matches))

        # Now fill in narration segments between dialogue
        current_pos = 0
        for dialogue in dialogue_matches:
            # Add narration before this dialogue
            if current_pos < dialogue['start']:
                narration_text = text[current_pos:dialogue['start']].strip()
                if narration_text:
                    segments.append(DialogueSegment(
                        text=narration_text,
                        speaker='narrator',
                        type='narration',
                        start_pos=current_pos,
                        end_pos=dialogue['start'],
                        confidence=1.0,
                    ))

            # Add dialogue
            segments.append(DialogueSegment(
                text=dialogue['text'],
                speaker=dialogue['speaker'],
                type='dialogue',
                start_pos=dialogue['start'],
                end_pos=dialogue['end'],
                confidence=dialogue['confidence'],
            ))

            current_pos = dialogue['end']

        # Add final narration if any
        if current_pos < len(text):
            narration_text = text[current_pos:].strip()
            if narration_text:
                segments.append(DialogueSegment(
                    text=narration_text,
                    speaker='narrator',
                    type='narration',
                    start_pos=current_pos,
                    end_pos=len(text),
                    confidence=1.0,
                ))

        # If no dialogue found, treat entire text as narration
        if not segments:
            logger.debug("No dialogue found, treating entire text as narration")
            segments.append(DialogueSegment(
                text=text,
                speaker='narrator',
                type='narration',
                start_pos=0,
                end_pos=len(text),
                confidence=1.0,
            ))

        return segments

    def _overlaps_existing(self, start: int, end: int, ranges: List[tuple]) -> bool:
        for used_start, used_end in ranges:
            if start < used_end and end > used_start:
                return True
        return False

    def _infer_speaker_from_context(self, text: str, dialogue_start: int, dialogue_end: int) -> Optional[str]:
        """Infer speaker from surrounding context

        Args:
            text: Full text
            dialogue_start: Start position of dialogue
            dialogue_end: End position of dialogue

        Returns:
            Character name or None
        """
        # Look at surrounding context (200 characters before and after)
        context_start = max(0, dialogue_start - 200)
        context_end = min(len(text), dialogue_end + 200)
        context = text[context_start:context_end]

        # Find character mentions in context, prioritizing those closer to the dialogue
        best_character = None
        min_distance = float('inf')

        for char_name in self.characters.keys():
            # Find all occurrences in context
            for match in re.finditer(
                r'\b' + re.escape(char_name) + r'\b',
                context,
                flags=re.IGNORECASE,
            ):
                match_pos = context_start + match.start()
                # Calculate distance from dialogue
                if match_pos < dialogue_start:
                    distance = dialogue_start - match_pos
                else:
                    distance = match_pos - dialogue_end

                if distance < min_distance:
                    min_distance = distance
                    best_character = char_name

        return best_character

    def _calculate_segment_confidence(
        self,
        speaker: Optional[str],
        speaker_position: str,
        is_known_character: bool,
    ) -> float:
        """Calculate a confidence score for a regex-detected dialogue segment.

        Scores:
          0.9  – attributed to a known character  (_CONF_KNOWN_SPEAKER)
          0.65 – attribution pattern matched but speaker not in known character
                 list, or resolved from surrounding context (_CONF_INFERRED_SPEAKER)
          0.5  – unattributed quoted text (_CONF_UNATTRIBUTED)
        """
        if speaker_position == 'none':
            return self._CONF_UNATTRIBUTED
        if is_known_character:
            return self._CONF_KNOWN_SPEAKER
        if speaker:
            return self._CONF_INFERRED_SPEAKER
        return self._CONF_UNATTRIBUTED

    def _find_narration_with_quotes(self, segments: List[DialogueSegment]) -> List[DialogueSegment]:
        """Return narration segments that contain an odd number of double-quotes.

        An odd quote count inside a narration block suggests the segment
        contains the tail of a multi-line quote or a broken/split quote.
        """
        broken = []
        for seg in segments:
            if seg.type != 'narration':
                continue
            quote_count = seg.text.count('"')
            if quote_count % 2 != 0:
                broken.append(seg)
                logger.debug(
                    "Potential broken quote in narration at %d-%d (%d unmatched quote char(s))",
                    seg.start_pos, seg.end_pos, quote_count,
                )
        return broken

    def _apply_llm_fallback_for_broken(
        self,
        full_text: str,
        segments: List[DialogueSegment],
    ) -> List[DialogueSegment]:
        """Replace broken narration segments using LLM-parsed sub-segments.

        Called after the primary LLM refinement pass so that segments with
        unbalanced quotes that could not be fixed by regex are re-parsed from
        scratch by the model.
        """
        if not self.use_llm:
            return segments

        broken = self._find_narration_with_quotes(segments)
        if not broken:
            return segments

        logger.info(
            "Running LLM fallback for %d potentially broken segment(s)", len(broken)
        )
        character_names = list(self.characters.keys())
        revised = list(segments)

        for seg in broken:
            result = self.llm.ask_json(
                system=(
                    "Parse this text for dialogue and narration. "
                    "Return strict JSON: "
                    "{\"segments\": [{\"text\": str, \"type\": \"dialogue\"|\"narration\"|\"thought\", \"speaker\": str|null}]} "
                    "where each item is a sequential portion of the input text."
                ),
                user={"text": seg.text, "characters": character_names},
            )
            parsed = result.get("segments")
            if not isinstance(parsed, list) or not parsed:
                logger.debug(
                    "LLM fallback returned no usable segments for broken block at %d",
                    seg.start_pos,
                )
                continue

            new_segs: List[DialogueSegment] = []
            offset = seg.start_pos
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                item_text = item.get("text", "")
                item_type = item.get("type", "narration")
                item_speaker = self._normalize_speaker_name(
                    item.get("speaker"), character_names
                )
                if item_type not in ("dialogue", "narration", "thought"):
                    item_type = "narration"
                if item_type == "narration" and not item_speaker:
                    item_speaker = "narrator"
                new_segs.append(
                    DialogueSegment(
                        text=item_text,
                        speaker=item_speaker,
                        type=item_type,
                        start_pos=offset,
                        end_pos=offset + len(item_text),
                        confidence=self._CONF_LLM_FALLBACK,
                    )
                )
                offset += len(item_text)

            if new_segs:
                idx = revised.index(seg)
                revised[idx : idx + 1] = new_segs
                logger.debug(
                    "LLM fallback replaced segment at %d with %d sub-segment(s)",
                    seg.start_pos, len(new_segs),
                )

        return revised

    def _validate_characters_with_llm(self, candidates: List[str]) -> List[str]:
        """Filter candidate names via LLM, keeping only actual person names.

        Sends the candidate list to the LLM and asks it to remove non-person
        entries (locations, objects, titles, etc.).  Falls back to the original
        list if the LLM is unavailable or returns an invalid response.
        """
        logger.debug(
            "Sending %d character candidate(s) to LLM for validation", len(candidates)
        )
        result = self.llm.ask_json(
            system=(
                "You are given a list of candidate names extracted from a novel. "
                "Filter to only proper character names (persons). "
                "Remove locations, titles, objects, and non-person words. "
                "Return strict JSON: {\"characters\": [list of valid character name strings]}"
            ),
            user={"candidates": candidates},
        )

        validated = result.get("characters")
        if not isinstance(validated, list):
            logger.debug(
                "LLM character validation returned no list; keeping all %d candidate(s)",
                len(candidates),
            )
            return candidates

        valid_lower = {str(n).strip().lower() for n in validated if isinstance(n, str)}
        filtered = [c for c in candidates if c.lower() in valid_lower]
        removed = sorted(set(candidates) - set(filtered))
        if removed:
            logger.info("LLM removed %d non-character candidate(s): %s", len(removed), removed)
        logger.debug(
            "LLM validated %d/%d candidates as character names",
            len(filtered), len(candidates),
        )
        return filtered

    def _refine_with_llm(self, full_text: str, segments: List[DialogueSegment]) -> List[DialogueSegment]:
        """Refine segment type and speaker attribution with Ollama."""
        character_names = list(self.characters.keys())
        if not character_names:
            character_names = []

        for segment in segments:
            context_start = max(0, segment.start_pos - 250)
            context_end = min(len(full_text), segment.end_pos + 250)
            context = full_text[context_start:context_end]

            classification = self.llm.ask_json(
                system=(
                    "Classify narrative text and infer speaker when possible. "
                    "Return strict JSON with keys type and speaker. "
                    "type must be one of dialogue, narration, thought. "
                    "speaker must be null or one of provided characters or narrator."
                ),
                user={
                    "text": segment.text,
                    "context": context,
                    "characters": character_names,
                    "current": {"type": segment.type, "speaker": segment.speaker},
                },
            )

            new_type = classification.get("type")
            if new_type in ("dialogue", "narration", "thought"):
                if new_type != segment.type:
                    logger.debug(
                        "LLM reclassified segment '%s' -> '%s': %.40r",
                        segment.type, new_type, segment.text,
                    )
                    segment.type = new_type
                    segment.confidence = min(1.0, segment.confidence + self._CONF_LLM_RECLASSIFY_BONUS)

            new_speaker = self._normalize_speaker_name(classification.get("speaker"), character_names)
            if new_speaker and new_speaker != segment.speaker:
                logger.debug(
                    "LLM updated speaker '%s' -> '%s': %.40r",
                    segment.speaker, new_speaker, segment.text,
                )
                segment.speaker = new_speaker
                segment.confidence = max(segment.confidence, self._CONF_LLM_SPEAKER_MIN)

            if segment.type in ("dialogue", "thought") and not segment.speaker:
                inferred = self.llm.ask_json(
                    system=(
                        "Infer the most likely speaker from context. "
                        "Return strict JSON: {\"speaker\": <name|null>} where speaker is null or one of characters."
                    ),
                    user={
                        "dialogue": segment.text,
                        "context": context,
                        "characters": character_names,
                    },
                )
                fallback_speaker = self._normalize_speaker_name(inferred.get("speaker"), character_names)
                if fallback_speaker:
                    logger.debug(
                        "LLM inferred speaker '%s' for unattributed segment: %.40r",
                        fallback_speaker, segment.text,
                    )
                    segment.speaker = fallback_speaker
                    segment.confidence = max(segment.confidence, self._CONF_LLM_SPEAKER_MIN)

            source_text = full_text[segment.start_pos:segment.end_pos]
            strict_type, strict_speaker = self._apply_strict_quote_rule(
                segment.text,
                segment.type,
                segment.speaker,
                source_text=source_text,
            )
            if strict_type != segment.type:
                logger.debug(
                    "Strict quote rule reclassified segment '%s' -> '%s': %.40r",
                    segment.type, strict_type, segment.text,
                )
                segment.type = strict_type
            if strict_type == "narration":
                segment.speaker = "narrator"
            elif strict_speaker:
                segment.speaker = strict_speaker

            if segment.type == "narration" and not segment.speaker:
                segment.speaker = "narrator"

        # Apply LLM fallback for segments with unbalanced quotes that regex
        # could not properly parse.
        segments = self._apply_llm_fallback_for_broken(full_text, segments)

        return segments

    def _normalize_speaker_name(self, speaker: Optional[str], characters: List[str]) -> Optional[str]:
        if not speaker:
            return None

        if not isinstance(speaker, str):
            return None

        cleaned = speaker.strip()
        if not cleaned:
            return None

        if self._is_narrator_name(cleaned):
            return "narrator"

        char_lookup = {name.casefold(): name for name in characters}
        return char_lookup.get(cleaned.casefold())

    def get_character_dialogue_counts(self) -> Dict[str, int]:
        """Get count of dialogue instances per character

        Returns:
            Dictionary mapping character names to dialogue counts
        """
        counts = {'narrator': 0}
        for char_name in self.characters.keys():
            counts[char_name] = 0

        for segment in self._last_segments:
            if not segment.is_dialogue:
                continue

            speaker = segment.speaker or 'narrator'
            counts[speaker] = counts.get(speaker, 0) + 1

        return counts

    def get_characters_with_gender(self) -> Dict[str, Optional[str]]:
        """Get all characters with their inferred genders

        Returns:
            Dictionary mapping character names to gender ('male', 'female', 'neutral', or None)
        """
        result = {}
        for char_name, char_profile in self.characters.items():
            result[char_name] = char_profile.gender
        return result


# Example usage
if __name__ == '__main__':
    # Example text with dialogue
    sample_text = """
    Alice walked into the room, looking around nervously.
    "Hello?" she called out. "Is anyone here?"
    Bob emerged from the shadows. "I've been waiting for you," he said with a smile.
    "You scared me!" Alice exclaimed, her hand on her chest.
    Bob laughed. "Sorry about that. I didn't mean to frighten you."
    They sat down at the table, and Alice began to explain her plan.
    "We need to move quickly," she said. "Time is running out."
    "I understand," Bob replied. "When do we leave?"
    "Tomorrow at dawn," Alice answered. "Be ready."
    """

    # Create detector
    detector = DialogueDetector()

    # Detect dialogue
    segments = detector.detect_dialogue_in_text(sample_text)

    # Display results
    print("Dialogue Detection Results:")
    print("=" * 50)
    for i, segment in enumerate(segments, 1):
        seg_type = "DIALOGUE" if segment.is_dialogue else "NARRATION"
        speaker = segment.speaker or "Unknown"
        preview = segment.text[:60] + "..." if len(segment.text) > 60 else segment.text
        print(f"{i}. [{seg_type}] {speaker}: {preview}")

    print("\n" + "=" * 50)
    print("Character Summary:")
    print("=" * 50)
    characters = detector.get_characters_with_gender()
    for char_name, gender in characters.items():
        print(f"  {char_name}: {gender or 'unknown'} gender")

    print("\n" + "=" * 50)
    print("Dialogue Counts:")
    print("=" * 50)
    counts = detector.get_character_dialogue_counts()
    for char_name, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {char_name}: {count} mentions")
