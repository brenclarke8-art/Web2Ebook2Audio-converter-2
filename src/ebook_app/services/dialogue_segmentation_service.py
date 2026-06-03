from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Literal

from ebook_app.services.llm_client import OllamaChatClient

SegmentType = Literal["dialogue", "thought", "narration", "general"]

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

    # Maximum characters to send to the LLM in a single request.
    # Kept for reference; the full cleaned text is sent in one pass.
    _MAX_LLM_CHARS = 4000

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
    ) -> DialogueLLMResult:
        cleaned = self.clean_text_for_llm(text)
        if not cleaned:
            return DialogueLLMResult(
                segments=[DialogueLLMSegment(text="", type="narration", speaker="narrator")],
                characters=[],
            )

        known_context = self._format_known_character_context(known_characters or [])
        hint_context = self._format_manual_segment_hints(manual_segment_hints or [])

        system_prompt = self._build_system_prompt(
            [block for block in (story_context_block, known_context) if block]
        )
        if hint_context:
            user_text = "\n\n".join((hint_context, cleaned))
        else:
            user_text = cleaned
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

    @staticmethod
    def _split_into_chunks(text: str, max_chars: int) -> list[str]:
        """Split *text* into chunks of at most *max_chars*, breaking at line boundaries.

        Prefers double-newline paragraph breaks; falls back to single-newline splits
        when the text contains no blank-line separators.
        """
        # Prefer paragraph-level splits (double newlines)
        double_units = re.split(r"\n\n+", text)
        if len(double_units) > 1:
            sep = "\n\n"
            units = double_units
        else:
            # No blank lines — split on individual lines instead
            sep = "\n"
            units = text.splitlines()

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for unit in units:
            unit_len = len(unit)
            sep_len = len(sep) if current else 0
            if current and current_len + sep_len + unit_len > max_chars:
                chunks.append(sep.join(current))
                current = [unit]
                current_len = unit_len
            else:
                current.append(unit)
                current_len += sep_len + unit_len

        if current:
            chunks.append(sep.join(current))

        return chunks

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
