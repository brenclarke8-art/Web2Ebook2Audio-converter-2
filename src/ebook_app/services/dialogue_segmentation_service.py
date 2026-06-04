from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import json
import logging
import re
import textwrap
from typing import Any, Iterable, Literal

from ebook_app.services.llm_client import OllamaChatClient

logger = logging.getLogger(__name__)

SegmentType = Literal["dialogue", "thought", "narration", "general"]

# Fraction of chunk size used as a backward-search window when snapping chunk
# boundaries to the nearest preceding newline.  A value of 10 means "search the
# last 10 % of the chunk" — large enough to find a paragraph break without
# walking too far back into already-processed text.
_CHUNK_BOUNDARY_SEARCH_FRACTION = 10

# Confidence assigned to speakers inferred from pass-2 attribution but not
# detected in pass-1 (i.e. characters the LLM attributed dialogue to without
# listing them explicitly in the character-detection pass).
_INFERRED_SPEAKER_CONFIDENCE = 0.85

_PASS_SHARED_RULES = """GLOBAL RULES
1. Do NOT invent characters.
2. Do NOT merge characters with similar names.
3. Do NOT infer relationships not explicitly stated.
4. Preserve the original line text exactly.
5. Preserve chronological order.
6. Output ONLY valid JSON and nothing else.
7. Never include trailing commas.
"""

_CHAR_DETECT_SYSTEM_PROMPT = """You are a deterministic character-extraction engine.
Identify all named characters who appear or are mentioned in the chapter.

CHARACTER DETECTION
Output ONLY:
[{ "name": "...", "gender": "male|female|unknown", "confidence": 0.0-1.0 }]

Rules:
- List every named character who appears or is mentioned.
- Use the most canonical name form seen in the text.
- Do NOT invent characters not present in the text.
- gender must be "male", "female", or "unknown".
- confidence is your certainty this is a distinct named character (0.0-1.0).
""" + _PASS_SHARED_RULES

_SEGMENT_ATTR_SYSTEM_PROMPT_PREFIX = """You are a deterministic dialogue-analysis engine.
For each provided line entry, classify the type and attribute the speaker or thinker.

SEGMENT AND ATTRIBUTE
Input: JSON array of {"id": "...", "text": "..."}
Output ONLY: [{"id": "...", "type": "dialogue|thought|narration", "speaker": "Name or narrator"}]

Rules:
- Return exactly one item per provided id, in the same order.
- Each item's "id" must match exactly one of the provided input ids.
- Do not omit or invent ids.
- type must be exactly one of: dialogue, thought, or narration.
- For narration lines, set speaker to "narrator".
- For dialogue and thought lines, use a name from KNOWN CHARACTERS, or "Unknown" if uncertain.
""" + _PASS_SHARED_RULES

_JSON_REPAIR_SYSTEM_PROMPT = """You are a JSON schema repair engine for a dialogue analysis pipeline.
You receive a SOURCE LIST of line IDs and a MALFORMED OR INVALID response from a prior model call.
Produce a valid JSON array with this exact schema:
[{"id": "...", "type": "dialogue|thought|narration", "speaker": "Name or narrator"}]

Rules:
- Include exactly one item per id from the SOURCE LIST. Do not omit or add ids.
- Each "id" must exactly match an id from the source list.
- "type" must be exactly: dialogue, thought, or narration.
- "speaker" must be a character name or "narrator" for narration lines.
- Preserve semantic meaning from the malformed response where discernible.
- Only repair JSON structure and schema — do not reinterpret story semantics.
- Output ONLY the JSON array. No commentary, no prose, no markdown fences.
"""

_DEFAULT_CHUNK_SIZE = 6000
_DEFAULT_CHUNK_OVERLAP = 500
# How many recent segments to inspect for overlap deduplication across chunks
_CHUNK_DEDUP_WINDOW = 15

_CHAPTER_SUMMARY_SYSTEM_PROMPT = """You are a concise chapter-summary assistant for a novel processing pipeline.
Given a chapter of fiction text, produce a brief summary covering:
- Named characters who appear and their roles
- Key events and actions
- Setting, mood, and important continuity details

Output ONLY valid JSON:
{"summary": "..."}

Rules:
- summary must be 2-4 sentences, under 200 words.
- Do NOT invent details not present in the text.
- Return ONLY the JSON object — no markdown fences, no extra keys.
"""


@dataclass
class DialogueLLMSegment:
    text: str
    type: SegmentType
    speaker: str | None


@dataclass
class ParseDiagnostics:
    """Parse-quality metadata for a single two-pass LLM result.

    Captured per-chunk and merged into the final chapter result so that
    the pipeline and UI can make informed review decisions.
    """
    malformed_json: bool = False
    validation_passed: bool = True
    id_match_ratio: float = 1.0
    fallback_count: int = 0
    repair_attempted: bool = False
    repair_succeeded: bool = False
    needs_review: bool = False


@dataclass
class DialogueLLMResult:
    segments: list[DialogueLLMSegment]
    characters: list[Any]
    diagnostics: ParseDiagnostics = field(default_factory=ParseDiagnostics)


class DialogueSegmentationService:
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
        # Web novel reader / app boilerplate
        r"←",                          # back-navigation arrows (← Back to novel, ← Previous)
        r"\bnext\s*[→»]",              # "Next →" forward navigation
        r"\bloading\s+chapter",        # "Loading chapter…"
        r"add\s+this\s+site\s+to",     # "Add this site to your home screen…"
        r"\bhome\s+screen\b",          # app-install prompts
        r"app[- ]like\s+reader",       # "app-like reader"
        r"\breader\s+mode\b",          # "Reader mode with saved preferences…"
        r"^chapter\s+\d+\s*$",        # standalone chapter-number header (no title after number)
        r"^novel\s*$",                 # lone "Novel" navigation label
        r"^install\b",                 # "Install" / "Install Fucknovelpia" prompts
        r"^later\s*$",                 # lone "Later" dismiss button
    )

    def __init__(
        self,
        *,
        client: OllamaChatClient,
        formatter_client: OllamaChatClient | None = None,
        strict_quotes: bool = False,
    ) -> None:
        self.client = client
        # Optional second model used exclusively for JSON repair/reformatting.
        # When None, repair is skipped and heuristic fallback is used instead.
        self.formatter_client = formatter_client
        self.strict_quotes = bool(strict_quotes)

    def parse(
        self,
        *,
        text: str,
        chapter_id: str,
        known_characters: list[str | dict[str, Any]] | None = None,
        manual_segment_hints: list[dict[str, str]] | None = None,
        story_context_block: str | None = None,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP,
    ) -> DialogueLLMResult:
        cleaned = self.clean_text_for_llm(text)
        if not cleaned:
            return DialogueLLMResult(
                segments=[DialogueLLMSegment(text="", type="narration", speaker="narrator")],
                characters=[],
            )

        known_chars = known_characters or []
        known_context = self._format_known_character_context(known_chars)
        hint_prefix = self._format_manual_segment_hints(manual_segment_hints or [])
        # Pass 0 (chapter summary): summarise the chapter text; used as pass-1 context
        summary_block = self._summarize_chapter(text=cleaned, chapter_id=chapter_id)
        # Pass 1 (character detection) receives: chapter summary + story context + known characters
        pass1_memory_blocks = [block for block in (summary_block, story_context_block, known_context) if block]

        # Route long chapters through the chunked path
        if len(cleaned) > chunk_size:
            result = self._parse_chunked(
                text=cleaned,
                known_characters=known_chars,
                pass1_memory_blocks=pass1_memory_blocks,
                hint_prefix=hint_prefix,
                chapter_id=chapter_id,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        else:
            result = self._parse_two_pass(
                text=cleaned,
                chapter_id=chapter_id,
                known_characters=known_chars,
                pass1_memory_blocks=pass1_memory_blocks,
                hint_prefix=hint_prefix,
            )

        if not result.segments:
            result = DialogueLLMResult(
                segments=[DialogueLLMSegment(text=cleaned, type="narration", speaker="narrator")],
                characters=result.characters,
            )

        return result

    def _parse_chunked(
        self,
        *,
        text: str,
        known_characters: list[str | dict[str, Any]],
        pass1_memory_blocks: list[str],
        hint_prefix: str,
        chapter_id: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> DialogueLLMResult:
        """Split *text* into overlapping chunks and merge results with dedup."""
        chunks = self._chunk_text(text, chunk_size, chunk_overlap)
        results: list[DialogueLLMResult] = []
        for i, chunk in enumerate(chunks):
            r = self._parse_two_pass(
                text=chunk,
                chapter_id=f"{chapter_id}_c{i}",
                known_characters=known_characters,
                pass1_memory_blocks=pass1_memory_blocks,
                hint_prefix=hint_prefix,
            )
            results.append(r)
        return self._merge_chunk_results(results)

    def _parse_two_pass(
        self,
        *,
        text: str,
        chapter_id: str,
        known_characters: list[str | dict[str, Any]],
        pass1_memory_blocks: list[str],
        hint_prefix: str,
    ) -> DialogueLLMResult:
        """Run the two-pass LLM pipeline for a single text block.

        Pass 1 — Character Detection:
          Semantic model: char-detect prompt + story context + known characters
          User:   original text
          Result: update known characters for pass 2

        Pass 2 — Segment and Attribute (ID-based):
          Semantic model: segment+attribute prompt + updated known characters
          User:   JSON array of {"id": "...", "text": "..."} line entries
          Result: per-line type (dialogue/thought/narration) and speaker keyed by id

        Repair Pass (optional):
          Formatter model: JSON repair prompt + source IDs + malformed response
          Only invoked when semantic pass-2 output fails ID validation.

        Fallback:
          When both semantic and repair attempts fail validation, heuristic
          classification is used and the result is flagged for review.
        """
        source_lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not source_lines:
            return DialogueLLMResult(
                segments=[DialogueLLMSegment(text=text, type="narration", speaker="narrator")],
                characters=[],
                diagnostics=ParseDiagnostics(),
            )

        # Assign stable IDs to each source line before calling the semantic model.
        id_lines = [{"id": f"{chapter_id}_L{i}", "text": line} for i, line in enumerate(source_lines)]
        valid_ids = {entry["id"] for entry in id_lines}

        # Pass 1: character detection (semantic model, raw text)
        pass1_system = self._build_pass_prompt(_CHAR_DETECT_SYSTEM_PROMPT, pass1_memory_blocks)
        pass1_raw = self._ask_json_any(
            system=pass1_system,
            user=text,
            chapter_id=f"{chapter_id}_p1",
        )
        detected_chars = self._normalize_char_detect(pass1_raw)

        # Merge pass-1 discoveries into known_characters for pass 2
        updated_known = self._merge_detected_into_known(known_characters, detected_chars)
        updated_known_context = self._format_known_character_context(updated_known)

        # Pass 2: ID-based segment classification + speaker attribution (semantic model)
        pass2_memory_blocks = [updated_known_context] if updated_known_context else []
        pass2_system = self._build_pass_prompt(_SEGMENT_ATTR_SYSTEM_PROMPT_PREFIX, pass2_memory_blocks)
        lines_payload = json.dumps(id_lines, ensure_ascii=False)
        pass2_user = "\n\n".join(part for part in (hint_prefix, lines_payload) if part)
        pass2_raw = self._ask_json_any(
            system=pass2_system,
            user=pass2_user,
            chapter_id=f"{chapter_id}_p2",
        )

        # Strict ID-based validation of semantic output
        diagnostics = ParseDiagnostics()
        items = self._coerce_list_payload(pass2_raw)
        is_valid, match_ratio = self._validate_id_items(items, valid_ids)
        diagnostics.id_match_ratio = match_ratio

        if not is_valid:
            diagnostics.malformed_json = True
            logger.warning(
                "Chapter %s: pass-2 semantic output failed ID validation "
                "(id_match_ratio=%.2f). %s",
                chapter_id,
                match_ratio,
                "Attempting formatter repair." if self.formatter_client else "No formatter client — using heuristic fallback.",
            )

            if self.formatter_client:
                # Repair pass: formatter model fixes structure only
                diagnostics.repair_attempted = True
                repaired = self._repair_with_formatter(
                    id_lines=id_lines,
                    malformed_response=pass2_raw,
                    chapter_id=f"{chapter_id}_p2r",
                )
                repaired_items = self._coerce_list_payload(repaired)
                is_valid2, match_ratio2 = self._validate_id_items(repaired_items, valid_ids)
                diagnostics.id_match_ratio = match_ratio2
                if is_valid2:
                    items = repaired_items
                    diagnostics.repair_succeeded = True
                    diagnostics.validation_passed = True
                    logger.info(
                        "Chapter %s: formatter repair succeeded (id_match_ratio=%.2f).",
                        chapter_id, match_ratio2,
                    )
                else:
                    logger.warning(
                        "Chapter %s: formatter repair also failed (id_match_ratio=%.2f). "
                        "Using heuristic fallback and flagging for review.",
                        chapter_id, match_ratio2,
                    )
                    diagnostics.validation_passed = False
                    diagnostics.needs_review = True
                    classified = self._heuristic_fallback_classify(source_lines)
                    diagnostics.fallback_count = len(source_lines)
                    return self._build_result_from_combined(classified, detected_chars, diagnostics)
            else:
                # No formatter available — safe heuristic fallback + flag for review
                diagnostics.validation_passed = False
                diagnostics.needs_review = True
                classified = self._heuristic_fallback_classify(source_lines)
                diagnostics.fallback_count = len(source_lines)
                return self._build_result_from_combined(classified, detected_chars, diagnostics)
        else:
            diagnostics.validation_passed = True

        # Convert validated ID-based items to line-based result list
        classified, fallback_count = self._normalize_id_items(items, id_lines)
        diagnostics.fallback_count = fallback_count
        if fallback_count > 0:
            diagnostics.needs_review = True

        return self._build_result_from_combined(classified, detected_chars, diagnostics)

    @staticmethod
    def _chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
        """Split *text* into overlapping chunks aligned to newline boundaries."""
        if not text or len(text) <= max_chars:
            return [text] if text else []

        chunks: list[str] = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + max_chars, text_len)
            if end < text_len:
                search_from = max(start, end - max(1, max_chars // _CHUNK_BOUNDARY_SEARCH_FRACTION))
                nl_pos = text.rfind("\n", search_from, end)
                if nl_pos > start:
                    end = nl_pos + 1
            chunks.append(text[start:end])
            if end >= text_len:
                break
            next_start = end - overlap
            if next_start <= start:
                next_start = start + 1
            nl_pos = text.find("\n", next_start, end)
            if nl_pos != -1:
                next_start = nl_pos + 1
            start = next_start

        return chunks

    @staticmethod
    def _merge_chunk_results(results: list[DialogueLLMResult]) -> DialogueLLMResult:
        """Merge per-chunk results, deduplicating overlapping segment texts."""
        seen_chars: set[str] = set()
        merged_chars: list[Any] = []
        merged_segs: list[DialogueLLMSegment] = []
        recent_texts: deque[str] = deque(maxlen=_CHUNK_DEDUP_WINDOW)

        # Merged diagnostics across all chunks
        merged_diag = ParseDiagnostics()

        for r in results:
            for c in r.characters:
                name = c["name"] if isinstance(c, dict) else str(getattr(c, "name", ""))
                key = name.casefold()
                if key and key not in seen_chars:
                    seen_chars.add(key)
                    merged_chars.append(c)
            for s in r.segments:
                norm = " ".join(s.text.split())
                if norm and norm not in recent_texts:
                    merged_segs.append(s)
                    recent_texts.append(norm)

            # Merge diagnostics
            d = r.diagnostics
            if d:
                if d.malformed_json:
                    merged_diag.malformed_json = True
                if not d.validation_passed:
                    merged_diag.validation_passed = False
                if d.repair_attempted:
                    merged_diag.repair_attempted = True
                    # repair_succeeded is True when at least one repair attempt
                    # succeeded; False when any attempt failed.  Track both so
                    # the caller can see partial-success scenarios.
                    if d.repair_succeeded:
                        merged_diag.repair_succeeded = True
                    else:
                        # Only downgrade to False if no earlier chunk succeeded.
                        if not merged_diag.repair_succeeded:
                            merged_diag.repair_succeeded = False
                if d.needs_review:
                    merged_diag.needs_review = True
                merged_diag.fallback_count += d.fallback_count

        # Average id_match_ratio across chunks
        valid_diags = [r.diagnostics for r in results if r.diagnostics is not None]
        if valid_diags:
            merged_diag.id_match_ratio = sum(d.id_match_ratio for d in valid_diags) / len(valid_diags)
        else:
            merged_diag.id_match_ratio = 1.0

        return DialogueLLMResult(
            segments=merged_segs,
            characters=merged_chars,
            diagnostics=merged_diag,
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
        return any(re.search(pattern, lowered) for pattern in cls._UI_NOISE_PATTERNS)

    @classmethod
    def clean_text_for_llm(cls, text: str) -> str:
        source = (text or "").strip()
        if not source:
            return ""
        lines = [line.strip() for line in source.splitlines()]
        kept = [line for line in lines if line and not cls._is_noise_line(line)]
        if not kept:
            return source
        cleaned = "\n".join(kept)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned or source

    def _build_result_from_combined(
        self,
        classified: list[dict],
        detected_chars: list[dict],
        diagnostics: ParseDiagnostics | None = None,
    ) -> DialogueLLMResult:
        """Build a DialogueLLMResult from the combined pass-2 output and pass-1 detected chars."""
        segments: list[DialogueLLMSegment] = []
        extra_char_confs: dict[str, float] = {}

        for item in classified:
            line = item["line"]
            seg_type = self._normalize_segment_type(item.get("type", "narration"))
            speaker_raw = str(item.get("speaker", "narrator")).strip() or "narrator"

            if seg_type == "narration":
                speaker = "narrator"
            else:
                # dialogue or thought: normalize speaker
                canonical = speaker_raw.strip() or "Unknown"
                if canonical.casefold() == "narrator":
                    canonical = "Unknown"
                speaker = canonical
                if speaker != "Unknown":
                    extra_char_confs[speaker] = max(extra_char_confs.get(speaker, 0.0), _INFERRED_SPEAKER_CONFIDENCE)

            if self.strict_quotes and seg_type in {"dialogue", "thought"} and not self._looks_quoted(line):
                seg_type = "narration"
                speaker = "narrator"

            segments.append(DialogueLLMSegment(text=line, type=seg_type, speaker=speaker))

        if not segments:
            return DialogueLLMResult(
                segments=[DialogueLLMSegment(text="", type="narration", speaker="narrator")],
                characters=[],
                diagnostics=diagnostics or ParseDiagnostics(),
            )

        # Combine characters: pass-1 detections take priority; add any speakers from pass-2
        all_chars: dict[str, dict] = {}
        for char in detected_chars:
            all_chars[char["name"].casefold()] = char
        for name, conf in extra_char_confs.items():
            key = name.casefold()
            if key not in all_chars:
                all_chars[key] = {"name": name, "gender": "unknown", "confidence": conf}

        return DialogueLLMResult(
            segments=segments,
            characters=list(all_chars.values()),
            diagnostics=diagnostics or ParseDiagnostics(),
        )

    @staticmethod
    def _normalize_segment_type(raw_type: Any) -> SegmentType:
        seg_type = str(raw_type or "narration").strip().lower()
        if seg_type == "general":
            seg_type = "narration"
        if seg_type not in {"dialogue", "thought", "narration"}:
            return "narration"
        return seg_type  # type: ignore[return-value]

    def _normalize_char_detect(self, payload: Any) -> list[dict]:
        """Normalize Pass 1 (character detection) LLM output.

        Expected: [{ "name": "...", "gender": "...", "confidence": 0.0-1.0 }]
        Also handles a single-object dict or a dict with a "name" key.
        """
        items = self._coerce_list_payload(payload)
        if not items and isinstance(payload, dict):
            if payload.get("name"):
                items = [payload]

        chars: list[dict] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            gender = str(item.get("gender", "unknown")).strip().lower()
            if gender not in {"male", "female"}:
                gender = "unknown"
            confidence = self._clamp_confidence(
                item.get("confidence", item.get("Confidence", 0.85))
            )
            chars.append({"name": name, "gender": gender, "confidence": confidence})
        return chars

    @staticmethod
    def _validate_id_items(items: list[Any], valid_ids: set[str]) -> tuple[bool, float]:
        """Validate that returned items have valid IDs.

        Returns (is_valid, id_match_ratio) where is_valid is True when at
        least 90 % of the expected IDs are present in *items*.
        """
        if not valid_ids:
            return True, 1.0
        if not items:
            return False, 0.0
        matched = sum(
            1 for item in items
            if isinstance(item, dict) and item.get("id") in valid_ids
        )
        ratio = matched / len(valid_ids)
        return ratio >= 0.9, ratio

    def _normalize_id_items(
        self,
        items: list[Any],
        id_lines: list[dict],
    ) -> tuple[list[dict], int]:
        """Convert validated ID-based pass-2 items into a line-keyed result list.

        For any line ID not present in the response, a per-line heuristic
        fallback is used instead of positional remapping.

        Returns (classified_list, fallback_count) where *fallback_count* is
        the number of lines that needed heuristic classification.
        """
        id_to_item: dict[str, dict] = {}
        for item in items:
            if isinstance(item, dict):
                id_val = str(item.get("id", "")).strip()
                if id_val:
                    # Keep first occurrence; reject duplicate IDs silently
                    id_to_item.setdefault(id_val, item)

        result: list[dict] = []
        fallback_count = 0
        for entry in id_lines:
            line_id = entry["id"]
            line_text = entry["text"]
            item = id_to_item.get(line_id)
            if item:
                seg_type = self._normalize_segment_type(item.get("type"))
                speaker = str(item.get("speaker", "narrator")).strip() or "narrator"
                result.append({"line": line_text, "type": seg_type, "speaker": speaker})
            else:
                # Heuristic-only fallback for this specific line; no positional remapping
                fallback_count += 1
                seg_type = self._fallback_line_type(line_text)
                result.append({"line": line_text, "type": seg_type, "speaker": "narrator"})

        return result, fallback_count

    def _heuristic_fallback_classify(self, source_lines: list[str]) -> list[dict]:
        """Classify all source lines using heuristics only (no LLM output)."""
        return [
            {
                "line": line,
                "type": self._fallback_line_type(line),
                "speaker": "narrator",
            }
            for line in source_lines
        ]

    def _repair_with_formatter(
        self,
        *,
        id_lines: list[dict],
        malformed_response: Any,
        chapter_id: str,
    ) -> Any:
        """Use the formatter model to repair a malformed/invalid pass-2 response.

        The formatter model is given the original ID'd source list and the
        malformed output and is instructed to produce schema-valid JSON without
        altering semantic content.
        """
        source_json = json.dumps(id_lines, ensure_ascii=False)
        malformed_str = (
            json.dumps(malformed_response, ensure_ascii=False)
            if not isinstance(malformed_response, str)
            else malformed_response
        )
        user = (
            f"SOURCE LIST:\n{source_json}\n\n"
            f"MALFORMED RESPONSE:\n{malformed_str}"
        )
        return self._ask_formatter_json_any(
            system=_JSON_REPAIR_SYSTEM_PROMPT,
            user=user,
            chapter_id=chapter_id,
        )

    def _normalize_pass_combined(
        self,
        payload: Any,
        source_lines: list[str],
    ) -> list[dict]:
        """Legacy normalizer for old-style pass-2 (line-keyed) LLM output.

        This method is kept for backward compatibility with direct callers that
        still use the old ``{"line": "...", "type": ..., "speaker": ...}`` format.
        Positional remapping has been removed; lines not found by exact text
        match receive a heuristic fallback instead.
        """
        items = self._coerce_list_payload(payload)
        if not items and isinstance(payload, dict):
            if "line" in payload:
                items = [payload]
            else:
                for line_key, value in payload.items():
                    if not isinstance(line_key, str):
                        continue
                    line_text = line_key.strip()
                    if not line_text:
                        continue
                    if isinstance(value, str):
                        items.append({"line": line_text, "type": value, "speaker": "narrator"})
                    elif isinstance(value, dict):
                        seg_type = (
                            value.get("type")
                            or value.get("label")
                            or value.get("classification")
                            or "narration"
                        )
                        speaker = (
                            value.get("speaker")
                            or value.get("name")
                            or value.get("character")
                            or "narrator"
                        )
                        items.append({"line": line_text, "type": seg_type, "speaker": speaker})

        # Build exact-text lookup; no positional remapping
        by_line: dict[str, deque[dict]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            line = str(item.get("line", "")).strip()
            if not line:
                continue
            seg_type = self._normalize_segment_type(item.get("type"))
            speaker = str(item.get("speaker", "narrator")).strip() or "narrator"
            entry = {"line": line, "type": seg_type, "speaker": speaker}
            by_line.setdefault(line, deque()).append(entry)

        result: list[dict] = []
        for line in source_lines:
            queue = by_line.get(line)
            if queue:
                entry = dict(queue.popleft())
            else:
                # Heuristic fallback — no positional remapping
                seg_type = self._fallback_line_type(line)
                entry = {"line": line, "type": seg_type, "speaker": "narrator"}
            result.append(entry)
        return result

    @staticmethod
    def _merge_detected_into_known(
        known_characters: list[str | dict[str, Any]],
        detected_chars: list[dict],
    ) -> list[str | dict[str, Any]]:
        """Return a new list with pass-1 detected characters merged into known_characters."""
        existing: set[str] = set()
        for item in known_characters:
            if isinstance(item, str):
                existing.add(item.casefold())
            elif isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                if name:
                    existing.add(name.casefold())

        result: list[str | dict[str, Any]] = list(known_characters)
        for char in detected_chars:
            name = char.get("name", "")
            if not name or name.casefold() in existing:
                continue
            existing.add(name.casefold())
            result.append(
                {
                    "name": name,
                    "gender": char.get("gender", "unknown"),
                    "confidence": char.get("confidence", 0.85),
                }
            )
        return result

    @staticmethod
    def _clamp_confidence(raw_value: Any) -> float:
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return 0.0
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value

    @staticmethod
    def _coerce_list_payload(payload: Any) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            # Single item with known schema keys (legacy "line" or new ID-based "id")
            if "line" in payload or "id" in payload:
                return [payload]
            for key in ("items", "lines", "results", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    def _summarize_chapter(self, *, text: str, chapter_id: str) -> str:
        """Pass 0: Ask the LLM to summarise the chapter for use as pass-1 context.

        Returns a formatted context block string, or an empty string if the call
        fails or the LLM returns no usable summary.
        """
        try:
            raw = self._ask_json_any(
                system=_CHAPTER_SUMMARY_SYSTEM_PROMPT,
                user=text,
                chapter_id=f"{chapter_id}_p0",
            )
            if isinstance(raw, dict):
                summary = str(raw.get("summary", "")).strip()
            elif isinstance(raw, str):
                summary = raw.strip()
            else:
                return ""
            if summary:
                return f"CHAPTER SUMMARY:\n{summary}"
        except Exception:
            logger.warning(
                "Chapter summary (pass 0) failed for %s — continuing without.",
                chapter_id,
                exc_info=True,
            )
        return ""

    def _ask_json_any(self, *, system: str, user: str, chapter_id: str) -> Any:
        ask_json_any = getattr(self.client, "ask_json_any", None)
        if callable(ask_json_any):
            return ask_json_any(system=system, user=user, chapter_id=chapter_id)
        ask_json = getattr(self.client, "ask_json")
        return ask_json(system=system, user=user, chapter_id=chapter_id)

    def _ask_formatter_json_any(self, *, system: str, user: str, chapter_id: str) -> Any:
        """Call the formatter model (if available) for JSON repair/reformatting tasks."""
        if not self.formatter_client:
            return {}
        ask_json_any = getattr(self.formatter_client, "ask_json_any", None)
        if callable(ask_json_any):
            return ask_json_any(system=system, user=user, chapter_id=chapter_id)
        ask_json = getattr(self.formatter_client, "ask_json")
        return ask_json(system=system, user=user, chapter_id=chapter_id)

    @staticmethod
    def _fallback_line_type(line: str) -> SegmentType:
        clean = (line or "").strip()
        if not clean:
            return "narration"
        if DialogueSegmentationService._looks_quoted(clean):
            return "dialogue"
        if clean.startswith(("(", "[", "【")) and clean.endswith((")", "]", "】")):
            return "thought"
        return "narration"

    @staticmethod
    def _looks_quoted(text: str) -> bool:
        clean = (text or "").strip()
        return (
            (len(clean) >= 2 and clean.startswith('"') and clean.endswith('"'))
            or (len(clean) >= 2 and clean.startswith("“") and clean.endswith("”"))
            or bool(re.search(r'"[^"\n]+"', clean))
        )

    @staticmethod
    def _build_pass_prompt(base_prompt: str, memory_blocks: Iterable[str]) -> str:
        blocks = [stripped for block in memory_blocks if (stripped := str(block).strip())]
        if not blocks:
            return base_prompt
        context_block = "CONTEXT (from previous chapters):\n" + "\n\n".join(blocks)
        return textwrap.dedent(f"{base_prompt}\n\n{context_block}").strip()

    @staticmethod
    def _format_known_character_context(known_characters: list[str | dict[str, Any]]) -> str:
        lines: list[str] = []
        for item in known_characters:
            if isinstance(item, str):
                name = item.strip()
                if name:
                    lines.append(f"- {name}")
                continue
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            parts = [name]
            aliases = item.get("aliases", [])
            if isinstance(aliases, list):
                cleaned_aliases: list[str] = []
                for alias in aliases:
                    if not isinstance(alias, str):
                        continue
                    alias_clean = alias.strip()
                    if alias_clean:
                        cleaned_aliases.append(alias_clean)
                if cleaned_aliases:
                    parts.append(f"aliases={'; '.join(cleaned_aliases)}")
            gender = str(item.get("gender", "")).strip().lower()
            if gender in {"male", "female"}:
                parts.append(f"gender={gender}")
            description = str(item.get("description", "")).strip()
            if description:
                parts.append(f"description={description}")
            lines.append(f"- {' | '.join(parts)}")

        if not lines:
            return ""

        return (
            "KNOWN CHARACTER CONTEXT (canonical names):\n"
            + "\n".join(lines)
            + "\nUse canonical names from this list when alias/title forms clearly match.\n"
            + "If attribution is ambiguous, use unknown."
        )

    @staticmethod
    def _format_manual_segment_hints(manual_segment_hints: list[dict[str, str]]) -> str:
        if not manual_segment_hints:
            return ""

        lines: list[str] = []
        for item in manual_segment_hints[:40]:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            speaker = str(item.get("speaker", "")).strip()
            seg_type = str(item.get("type", "")).strip().lower()
            if not text or not speaker:
                continue
            if seg_type not in {"dialogue", "thought", "narration"}:
                seg_type = "dialogue"
            snippet = " ".join(text.split())
            if len(snippet) > 180:
                snippet = f"{snippet[:177]}..."
            lines.append(f'- "{snippet}" => speaker={speaker}, type={seg_type}')

        if not lines:
            return ""

        return (
            "MANUAL REVIEW CORRECTIONS (authoritative, user-approved):\n"
            + "\n".join(lines)
            + "\nTreat these corrections as ground truth when assigning speakers and segment types."
        )
