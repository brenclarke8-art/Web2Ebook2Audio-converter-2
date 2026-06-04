from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import re
import textwrap
from typing import Any, Iterable, Literal

from ebook_app.services.llm_client import OllamaChatClient

SegmentType = Literal["dialogue", "thought", "narration", "general"]

# Fraction of chunk size used as a backward-search window when snapping chunk
# boundaries to the nearest preceding newline.  A value of 10 means "search the
# last 10 % of the chunk" — large enough to find a paragraph break without
# walking too far back into already-processed text.
_CHUNK_BOUNDARY_SEARCH_FRACTION = 10

_PASS_SHARED_RULES = """GLOBAL RULES
1. Do NOT invent characters.
2. Do NOT merge characters with similar names.
3. Do NOT infer relationships not explicitly stated.
4. Preserve the original line text exactly.
5. Preserve chronological order.
6. Output ONLY valid JSON and nothing else.
7. Never include trailing commas.
"""

_PASS1_SYSTEM_PROMPT_PREFIX = """You are a deterministic text-analysis engine.
Split the chapter into line-level semantic labels.

PASS 1 — Line Classification
Output ONLY:
[{ "line": "...", "type": "dialogue|thought|narration" }]

Allowed type values: dialogue, thought, narration.
Classify each non-empty line exactly once.
""" + _PASS_SHARED_RULES

_PASS2_SYSTEM_PROMPT_PREFIX = """You are a deterministic speaker-attribution engine.
You will receive dialogue lines only.

PASS 2 — Speaker Attribution
Output ONLY:
[{ "line": "...", "speaker": "Name or Unknown", "Confidence": "0-1" }]

Rules:
- Return one item per provided dialogue line.
- If uncertain, speaker must be "Unknown".
- Confidence must be numeric in [0, 1].
""" + _PASS_SHARED_RULES

_DEFAULT_CHUNK_SIZE = 6000
_DEFAULT_CHUNK_OVERLAP = 500
# How many recent segments to inspect for overlap deduplication across chunks
_CHUNK_DEDUP_WINDOW = 15


@dataclass
class DialogueLLMSegment:
    text: str
    type: SegmentType
    speaker: str | None


@dataclass
class DialogueLLMResult:
    segments: list[DialogueLLMSegment]
    characters: list[Any]


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

    def __init__(self, *, client: OllamaChatClient, strict_quotes: bool = False) -> None:
        self.client = client
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

        known_context = self._format_known_character_context(known_characters or [])
        hint_prefix = self._format_manual_segment_hints(manual_segment_hints or [])
        memory_blocks = [block for block in (story_context_block, known_context) if block]

        # Route long chapters through the chunked path
        if len(cleaned) > chunk_size:
            result = self._parse_chunked(
                text=cleaned,
                memory_blocks=memory_blocks,
                hint_prefix=hint_prefix,
                chapter_id=chapter_id,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        else:
            result = self._parse_three_pass(
                text=cleaned,
                chapter_id=chapter_id,
                memory_blocks=memory_blocks,
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
        memory_blocks: list[str],
        hint_prefix: str,
        chapter_id: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> DialogueLLMResult:
        """Split *text* into overlapping chunks and merge results with dedup."""
        chunks = self._chunk_text(text, chunk_size, chunk_overlap)
        results: list[DialogueLLMResult] = []
        for i, chunk in enumerate(chunks):
            r = self._parse_three_pass(
                text=chunk,
                chapter_id=f"{chapter_id}_c{i}",
                memory_blocks=memory_blocks,
                hint_prefix=hint_prefix,
            )
            results.append(r)
        return self._merge_chunk_results(results)

    def _parse_three_pass(
        self,
        *,
        text: str,
        chapter_id: str,
        memory_blocks: list[str],
        hint_prefix: str,
    ) -> DialogueLLMResult:
        source_lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not source_lines:
            return DialogueLLMResult(
                segments=[DialogueLLMSegment(text=text, type="narration", speaker="narrator")],
                characters=[],
            )

        pass1_system = self._build_pass_prompt(_PASS1_SYSTEM_PROMPT_PREFIX, memory_blocks)
        pass1_user = text
        pass1_raw = self._ask_json_any(
            system=pass1_system,
            user=pass1_user,
            chapter_id=f"{chapter_id}_p1",
        )
        classified = self._normalize_pass1(pass1_raw, source_lines)

        dialogue_lines = [item["line"] for item in classified if item["type"] == "dialogue"]
        attributions: dict[str, deque[tuple[str, float]]] = {}
        if dialogue_lines:
            pass2_system = self._build_pass_prompt(_PASS2_SYSTEM_PROMPT_PREFIX, memory_blocks)
            dialogue_block = "\n".join(f"- {line}" for line in dialogue_lines)
            pass2_user = "\n\n".join(
                part
                for part in (
                    hint_prefix,
                    "DIALOGUE LINES (attribute speaker for each line):",
                    dialogue_block,
                    "FULL CHAPTER TEXT:",
                    text,
                )
                if part
            )
            pass2_raw = self._ask_json_any(
                system=pass2_system,
                user=pass2_user,
                chapter_id=f"{chapter_id}_p2",
            )
            attributions = self._normalize_pass2(pass2_raw)

        return self._build_final_result(classified, attributions)

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

        return DialogueLLMResult(segments=merged_segs, characters=merged_chars)

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

    def _build_final_result(
        self,
        classified: list[dict[str, str]],
        attributions: dict[str, deque[tuple[str, float]]],
    ) -> DialogueLLMResult:
        segments: list[DialogueLLMSegment] = []
        character_best_conf: dict[str, float] = {}

        for item in classified:
            line = item["line"]
            seg_type = self._normalize_segment_type(item["type"])
            speaker: str | None = None
            speaker_conf = 0.0

            if seg_type == "dialogue":
                attribution_queue = attributions.get(line)
                if attribution_queue:
                    speaker, speaker_conf = attribution_queue.popleft()
                if not speaker:
                    speaker = "Unknown"
                    speaker_conf = 0.0
                canonical = speaker.strip() or "Unknown"
                if canonical.casefold() in {"unknown", "narrator"}:
                    canonical = "Unknown"
                speaker = canonical
                if speaker != "Unknown":
                    existing_conf = character_best_conf.get(speaker, 0.0)
                    character_best_conf[speaker] = max(existing_conf, speaker_conf)
            elif seg_type == "narration":
                speaker = "narrator"

            if self.strict_quotes and seg_type in {"dialogue", "thought"} and not self._looks_quoted(line):
                seg_type = "narration"
                speaker = "narrator"

            segments.append(DialogueLLMSegment(text=line, type=seg_type, speaker=speaker))

        if not segments:
            return DialogueLLMResult(
                segments=[DialogueLLMSegment(text="", type="narration", speaker="narrator")],
                characters=[],
            )

        characters = [
            {"name": name, "gender": "unknown", "confidence": conf}
            for name, conf in character_best_conf.items()
        ]
        return DialogueLLMResult(segments=segments, characters=characters)

    @staticmethod
    def _normalize_segment_type(raw_type: Any) -> SegmentType:
        seg_type = str(raw_type or "narration").strip().lower()
        if seg_type == "general":
            seg_type = "narration"
        if seg_type not in {"dialogue", "thought", "narration"}:
            return "narration"
        return seg_type  # type: ignore[return-value]

    def _normalize_pass1(
        self,
        payload: Any,
        source_lines: list[str],
    ) -> list[dict[str, str]]:
        items = self._coerce_list_payload(payload)
        by_line: dict[str, deque[str]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            line = str(item.get("line", "")).strip()
            if not line:
                continue
            seg_type = self._normalize_segment_type(item.get("type"))
            by_line.setdefault(line, deque()).append(seg_type)

        classified: list[dict[str, str]] = []
        for line in source_lines:
            queue = by_line.get(line)
            seg_type = queue.popleft() if queue else self._fallback_line_type(line)
            classified.append({"line": line, "type": seg_type})
        return classified

    def _normalize_pass2(
        self,
        payload: Any,
    ) -> dict[str, deque[tuple[str, float]]]:
        items = self._coerce_list_payload(payload)
        by_line: dict[str, deque[tuple[str, float]]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            line = str(item.get("line", "")).strip()
            if not line:
                continue
            speaker = str(item.get("speaker", "Unknown")).strip() or "Unknown"
            confidence = self._clamp_confidence(item.get("Confidence", item.get("confidence", 0.0)))
            by_line.setdefault(line, deque()).append((speaker, confidence))
        return by_line

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
            for key in ("items", "lines", "results", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    def _ask_json_any(self, *, system: str, user: str, chapter_id: str) -> Any:
        ask_json_any = getattr(self.client, "ask_json_any", None)
        if callable(ask_json_any):
            return ask_json_any(system=system, user=user, chapter_id=chapter_id)
        ask_json = getattr(self.client, "ask_json")
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
