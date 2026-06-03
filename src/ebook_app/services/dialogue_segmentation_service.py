from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal

from ebook_app.services.llm_client import OllamaChatClient

SegmentType = Literal["dialogue", "thought", "narration", "general"]

_SEGMENTATION_SYSTEM_PROMPT = """You are a text‑segmentation and character‑extraction engine.
Your job is to analyze the provided novel text and output a STRICT JSON object.
Follow ALL rules exactly. Never add fields not defined here. Never hallucinate.

============================================================
GLOBAL RULES
============================================================
1. You MUST return valid JSON. No comments, no explanations, no prose.
2. You MUST segment the text in reading order.
3. You MUST NOT invent characters, genders, or speakers.
4. If uncertain, use "unknown" and reduce confidence.
5. You MUST preserve the original text exactly for each segment.
6. You MUST NOT merge or split sentences unless required by the rules below.
7. You MUST NOT infer emotions, motivations, or hidden meaning.

============================================================
SEGMENTATION RULES
============================================================
Segment the text into the following types:

- "dialogue" → text inside quotes spoken aloud by a character.
- "thought" → internal monologue, often italicized or marked with special brackets.
- "narration" → everything else.

Each segment MUST contain:
- the exact text
- the type
- the speaker (if known)
- the speaker_gender (if known)
- speaker_confidence (0–1)
- gender_confidence (0–1)
- character_confidence (0–1)
- paragraph_id (stable ID based on paragraph order)

============================================================
SPEAKER ATTRIBUTION RULES
============================================================
Assign a speaker ONLY when:
- the speaker is explicitly named in the same paragraph, OR
- the speaker is unambiguously the only possible character speaking.

If ambiguous:
- speaker = "unknown"
- speaker_confidence = 0.0

NEVER guess based on tone, personality, or narrative style.
When a known-character context block is provided, prefer the canonical known name
when a title/alias form clearly points to that known character.
If multiple known characters could match, use "unknown".

============================================================
GENDER RULES
============================================================
Assign gender ONLY when:
- explicitly stated (he/she, boy/girl, man/woman)
- strongly implied by name with high certainty

If uncertain:
- speaker_gender = "unknown"
- gender_confidence = 0.0

============================================================
CHARACTER LIST RULES
============================================================
Extract ALL characters explicitly mentioned in the text.
For each character include:
- name
- gender (if known)
- gender_confidence (0–1)

Do NOT include:
- inferred characters
- unnamed characters ("the guard", "the teacher")

============================================================
JSON OUTPUT FORMAT
============================================================

{
  "characters": [
    {
      "name": "string",
      "gender": "male | female | unknown",
      "gender_confidence": 0.0
    }
  ],
  "segments": [
    {
      "paragraph_id": "p001",
      "text": "string",
      "type": "dialogue | thought | narration",
      "speaker": "string",
      "speaker_gender": "male | female | unknown",
      "speaker_confidence": 0.0,
      "gender_confidence": 0.0,
      "character_confidence": 0.0
    }
  ]
}

============================================================
BEGIN INPUT TEXT
============================================================
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
    # Chapters longer than this are split at paragraph boundaries.
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
    ) -> DialogueLLMResult:
        cleaned = self.clean_text_for_llm(text)
        if not cleaned:
            return DialogueLLMResult(
                segments=[DialogueLLMSegment(text="", type="narration", speaker="narrator")],
                characters=[],
            )

        known_context = self._format_known_character_context(known_characters or [])
        hint_context = self._format_manual_segment_hints(manual_segment_hints or [])
        chunks = (
            [cleaned]
            if len(cleaned) <= self._MAX_LLM_CHARS
            else self._split_into_chunks(cleaned, self._MAX_LLM_CHARS)
        )

        all_segments: list[DialogueLLMSegment] = []
        all_characters: list[Any] = []
        seen_chars: set[str] = set()

        for i, chunk in enumerate(chunks):
            chunk_id = f"{chapter_id}_c{i}" if len(chunks) > 1 else chapter_id
            # Send the chapter text as plain text so it follows "BEGIN INPUT TEXT"
            # in the system prompt naturally. Prepend known characters when available.
            context_blocks = [block for block in (known_context, hint_context) if block]
            if context_blocks:
                user_text = "\n\n".join(context_blocks + [chunk])
            else:
                user_text = chunk
            raw = self.client.ask_json(
                system=_SEGMENTATION_SYSTEM_PROMPT, user=user_text, chapter_id=chunk_id
            )
            result = self._normalize_payload(raw, source_text=chunk)
            all_segments.extend(result.segments)
            for c in result.characters:
                key = (c if isinstance(c, str) else c.get("name", "")).casefold()
                if key and key not in seen_chars:
                    seen_chars.add(key)
                    all_characters.append(c)

        if not all_segments:
            all_segments = [DialogueLLMSegment(text=cleaned, type="narration", speaker="narrator")]

        return DialogueLLMResult(segments=all_segments, characters=all_characters)

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
