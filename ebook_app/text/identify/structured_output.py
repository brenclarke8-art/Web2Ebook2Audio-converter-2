# ebook_app/text/identify/structured_output.py
"""
Structured LLM-output parsing pipeline.

Provides:
- Pydantic schema for LLM extraction output validation.
- CharacterRegistry for persistent speaker_name -> character_id mapping.
- sanitize_json_text() — strips code fences and finds embedded JSON.
- parse_structured_llm_response() — validates against schema with one repair attempt.
- normalize_segments() — post-processes segments: drops empty, assigns fallback
  speaker, normalises type, and attaches character_id via CharacterRegistry.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, ValidationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Controlled type enum
# ---------------------------------------------------------------------------
CharacterType = Literal["dialogue", "thought", "narration", "system"]

_VALID_TYPES: frozenset[str] = frozenset({"dialogue", "thought", "narrator", "narration", "system"})
_TYPE_ALIAS: dict[str, str] = {
    "narration": "narration",
    "narrator": "narration",
    "dialogue": "dialogue",
    "thought": "thought",
    "system": "system",
}


def _coerce_type(value: str | None) -> str:
    """Map any incoming type string to a canonical value, defaulting to 'narration'."""
    lowered = (value or "").strip().lower()
    return _TYPE_ALIAS.get(lowered, "narration")


# ---------------------------------------------------------------------------
# Pydantic schema
# ---------------------------------------------------------------------------

class LLMSegmentInput(BaseModel):
    """Schema for a single segment returned by the LLM."""

    line_id: str = Field(default="", description="Stable identifier for this segment.")
    raw_text: str = Field(default="", description="Original text as found in the source.")
    normalized_text: str = Field(default="", description="Clean, TTS-ready text (stripped).")
    speaker_name: Optional[str] = Field(default=None, description="Speaker name or None.")
    speaker_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    character_type: str = Field(default="narration", description="One of dialogue/thought/narration/system.")
    voice_hint: Optional[str] = Field(default=None, description="Optional TTS voice hint.")

    @field_validator("character_type", mode="before")
    @classmethod
    def _coerce_character_type(cls, v: Any) -> str:
        return _coerce_type(str(v) if v is not None else "narration")

    @field_validator("normalized_text", mode="before")
    @classmethod
    def _strip_normalized(cls, v: Any) -> str:
        return (str(v) if v is not None else "").strip()

    @field_validator("speaker_confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v: Any) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0


class LLMResultInput(BaseModel):
    """Top-level envelope for a structured LLM extraction response."""

    segments: List[LLMSegmentInput] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Character registry
# ---------------------------------------------------------------------------

class CharacterRegistry:
    """
    Maps speaker names to persistent character IDs.

    Names are normalised to lower-case for lookup so that "ALICE" and "Alice"
    resolve to the same character.  The display_name always stores the first
    casing encountered.
    """

    def __init__(self) -> None:
        self._by_name: dict[str, dict[str, str]] = {}
        self._next_id: int = 1

    def get_or_create(self, speaker_name: str) -> dict[str, str]:
        """Return the character record for *speaker_name*, creating one if needed."""
        key = speaker_name.strip().lower()
        if not key:
            key = "unknown"
        if key not in self._by_name:
            self._by_name[key] = {
                "character_id": f"char_{self._next_id}",
                "display_name": speaker_name.strip() or "Unknown",
            }
            self._next_id += 1
        return self._by_name[key]

    def all_characters(self) -> list[dict[str, str]]:
        """Return all registered character records."""
        return list(self._by_name.values())


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------
def sanitize_json_text(raw: str) -> str:
    """
    Strip markdown code fences and extract the first JSON object or array.

    Returns the cleaned string, ready for ``json.loads()``.
    Raises ``ValueError`` if no JSON-like content is found.
    """
    text = (raw or "").strip()

    # Remove opening code fence line (```json … ```)
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Fast path: already valid JSON
    try:
        json.loads(text)
        return text
    except Exception:
        pass

    # Find the first { or [ and match to the last } or ]
    obj_start = text.find("{")
    arr_start = text.find("[")
    candidates = [i for i in (obj_start, arr_start) if i != -1]
    if not candidates:
        raise ValueError(
            f"No JSON-like content found in LLM response. Received: {raw[:100]!r}..."
        )
    start = min(candidates)
    last_obj = text.rfind("}")
    last_arr = text.rfind("]")
    end = max(last_obj, last_arr)
    if end <= start:
        raise ValueError(
            f"Could not locate matching JSON close bracket. "
            f"Found start at {start}, last '}}' at {last_obj}, last ']' at {last_arr}"
        )
    return text[start:end + 1]


# ---------------------------------------------------------------------------
# Structured response parser / validator
# ---------------------------------------------------------------------------

def parse_structured_llm_response(
    raw: str,
    *,
    repair_fn: Optional[Callable[[str], str]] = None,
    chapter_id: str = "",
) -> LLMResultInput:
    """
    Parse and validate an LLM JSON response against the ``LLMResultInput`` schema.

    Stages:
    1. Sanitize raw text (strip code fences, extract JSON).
    2. ``json.loads`` the sanitized text.
    3. Validate with Pydantic.
    4. If validation fails and *repair_fn* is provided, call it once and retry.

    Parameters
    ----------
    raw:
        Raw string returned by the LLM.
    repair_fn:
        Optional callable that accepts the raw broken response and returns a
        repaired JSON string.  Called at most once.
    chapter_id:
        Used only in log messages.

    Returns
    -------
    LLMResultInput
        A validated result.  Never raises; returns an empty result on terminal
        failure.
    """
    def _try_parse(text: str) -> LLMResultInput | None:
        try:
            clean = sanitize_json_text(text)
        except ValueError as exc:
            logger.debug("structured_output: sanitize failed chapter=%r: %s", chapter_id, exc)
            return None

        try:
            data = json.loads(clean)
        except json.JSONDecodeError as exc:
            logger.debug("structured_output: json.loads failed chapter=%r: %s", chapter_id, exc)
            return None

        # Accept bare list of segments
        if isinstance(data, list):
            data = {"segments": data}

        try:
            return LLMResultInput.model_validate(data)
        except ValidationError as exc:
            logger.warning(
                "structured_output: schema validation failed chapter=%r — %s",
                chapter_id,
                exc,
            )
            return None

    result = _try_parse(raw)
    if result is not None:
        return result

    if repair_fn is not None:
        logger.info(
            "structured_output: attempting repair pass for chapter=%r", chapter_id
        )
        try:
            repaired_raw = repair_fn(raw)
        except Exception as exc:
            logger.warning(
                "structured_output: repair_fn raised chapter=%r: %s", chapter_id, exc
            )
            repaired_raw = ""

        result = _try_parse(repaired_raw)
        if result is not None:
            logger.info(
                "structured_output: repair succeeded for chapter=%r", chapter_id
            )
            return result

        logger.warning(
            "structured_output: repair also failed chapter=%r — returning empty result",
            chapter_id,
        )

    return LLMResultInput(segments=[])


# ---------------------------------------------------------------------------
# Post-processing / normalisation
# ---------------------------------------------------------------------------

def normalize_segments(
    result: LLMResultInput,
    registry: CharacterRegistry,
    *,
    default_narrator: str = "Narrator",
    default_unknown: str = "Unknown",
) -> list[dict[str, Any]]:
    """
    Post-process validated segments into final pipeline-ready dicts.

    For each segment:
    - Drops segments whose ``normalized_text`` is empty/whitespace.
    - Determines a fallback speaker when ``speaker_name`` is missing:
      dialogue / thought → *default_unknown*; anything else → *default_narrator*.
    - Normalises ``character_type`` via ``_coerce_type``.
    - Resolves or creates a ``character_id`` in *registry*.

    Returns a list of dicts with guaranteed keys:
        line_id, text, segment_type, speaker, character_id, speaker_confidence, voice_hint
    """
    output: list[dict[str, Any]] = []
    for seg in result.segments:
        text = seg.normalized_text.strip()
        if not text:
            logger.debug(
                "structured_output: dropping empty segment line_id=%r", seg.line_id
            )
            continue

        seg_type = _coerce_type(seg.character_type)

        speaker_raw = (seg.speaker_name or "").strip()
        if not speaker_raw:
            speaker_raw = (
                default_unknown if seg_type in {"dialogue", "thought"} else default_narrator
            )

        char = registry.get_or_create(speaker_raw)

        output.append({
            "line_id": seg.line_id,
            "text": text,
            "segment_type": seg_type,
            "speaker": char["display_name"],
            "character_id": char["character_id"],
            "speaker_confidence": seg.speaker_confidence,
            "voice_hint": seg.voice_hint,
        })

    return output
