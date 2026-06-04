from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import re
from typing import Any, Iterable, Literal

from ebook_app.services.llm_client import OllamaChatClient

SegmentType = Literal["dialogue", "thought", "narration", "general"]

# Fraction of chunk size used as a backward-search window when snapping chunk
# boundaries to the nearest preceding newline.  A value of 10 means "search the
# last 10 % of the chunk" — large enough to find a paragraph break without
# walking too far back into already-processed text.
_CHUNK_BOUNDARY_SEARCH_FRACTION = 10

_SEGMENTATION_SYSTEM_PROMPT_PREFIX = """You are a deterministic text-analysis engine.
Your job is to parse a light-novel chapter into structured JSON with perfect consistency.
Follow the rules exactly. Do not explain anything. Do not add commentary.
Output ONLY valid JSON. If unsure, output an empty array or empty string instead of guessing.

========================
GLOBAL RULES
========================
1. Do NOT invent characters.
2. Do NOT merge characters with similar names.
3. Do NOT infer relationships not explicitly stated.
4. If a speaker is unknown, set "speaker": "Unknown".
5. Preserve the original order of all segments.
6. Never output prose outside the JSON.
7. Never include trailing commas.
8. If the chapter contains no dialogue or thoughts, return empty arrays for those fields.

========================
CHARACTER MEMORY (from previous chapters)
========================
"""

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

        system_prompt = self._build_system_prompt(
            [block for block in (story_context_block, known_context) if block]
        )

        # Route long chapters through the chunked path
        if len(cleaned) > chunk_size:
            result = self._parse_chunked(
                text=cleaned,
                system_prompt=system_prompt,
                hint_prefix=hint_prefix,
                chapter_id=chapter_id,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        else:
            user_text = "\n\n".join(part for part in (hint_prefix, cleaned) if part)
            raw = self.client.ask_json(
                system=system_prompt, user=user_text, chapter_id=chapter_id
            )
            result = self._normalize_payload(raw, source_text=cleaned)

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
        system_prompt: str,
        hint_prefix: str,
        chapter_id: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> DialogueLLMResult:
        """Split *text* into overlapping chunks and merge results with dedup."""
        chunks = self._chunk_text(text, chunk_size, chunk_overlap)
        results: list[DialogueLLMResult] = []
        for i, chunk in enumerate(chunks):
            user_text = "\n\n".join(part for part in (hint_prefix, chunk) if part)
            raw = self.client.ask_json(
                system=system_prompt,
                user=user_text,
                chapter_id=f"{chapter_id}_c{i}",
            )
            r = self._normalize_payload(raw, source_text=chunk)
            results.append(r)
        return self._merge_chunk_results(results)

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

    def _normalize_payload(self, payload: dict, *, source_text: str) -> DialogueLLMResult:
        raw_segments = payload.get("segments") if isinstance(payload, dict) else None
        segments: list[DialogueLLMSegment] = []
        characters: list[str] = []
        seen = set()

        if isinstance(payload, dict) and isinstance(payload.get("characters"), list):
            for item in payload["characters"]:
                if isinstance(item, str):
                    name = item.strip()
                    if name and name.casefold() != "narrator" and name.casefold() not in seen:
                        seen.add(name.casefold())
                        characters.append(name)
                elif isinstance(item, dict):
                    name = str(item.get("name", "")).strip()
                    if name and name.casefold() != "narrator" and name.casefold() not in seen:
                        confidence = item.get("confidence", 0.0)
                        try:
                            confidence_val = float(confidence)
                        except (TypeError, ValueError):
                            confidence_val = 0.0
                        seen.add(name.casefold())
                        characters.append(
                            {
                                "name": name,
                                "gender": str(item.get("gender", "unknown")).strip().lower() or "unknown",
                                "confidence": confidence_val,
                            }
                        )

        if isinstance(raw_segments, list):
            for item in raw_segments:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                seg_type = str(item.get("type", "narration")).strip().lower()
                if seg_type == "general":
                    seg_type = "narration"
                if seg_type not in {"dialogue", "thought", "narration"}:
                    seg_type = "narration"
                speaker_val = item.get("speaker")
                speaker = str(speaker_val).strip() if isinstance(speaker_val, str) else None
                if speaker and speaker.casefold() == "narrator":
                    speaker = "narrator"
                if seg_type == "narration" and not speaker:
                    speaker = "narrator"
                if self.strict_quotes and seg_type in {"dialogue", "thought"} and not self._looks_quoted(text):
                    seg_type = "narration"
                    speaker = "narrator"
                segments.append(DialogueLLMSegment(text=text, type=seg_type, speaker=speaker))
                if speaker and speaker.casefold() != "narrator" and speaker.casefold() not in seen:
                    seen.add(speaker.casefold())
                    characters.append(speaker)

        if not segments:
            segments = [DialogueLLMSegment(text=source_text, type="narration", speaker="narrator")]

        return DialogueLLMResult(segments=segments, characters=characters)

    @staticmethod
    def _looks_quoted(text: str) -> bool:
        clean = (text or "").strip()
        return (
            (len(clean) >= 2 and clean.startswith('"') and clean.endswith('"'))
            or (len(clean) >= 2 and clean.startswith("“") and clean.endswith("”"))
            or bool(re.search(r'"[^"\n]+"', clean))
        )

    @staticmethod
    def _build_system_prompt(memory_blocks: Iterable[str]) -> str:
        blocks = [stripped for block in memory_blocks if (stripped := str(block).strip())]
        if not blocks:
            return _SEGMENTATION_SYSTEM_PROMPT_PREFIX
        return _SEGMENTATION_SYSTEM_PROMPT_PREFIX + "\n\n" + "\n\n".join(blocks)

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
