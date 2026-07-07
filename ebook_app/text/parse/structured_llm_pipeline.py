"""
Structured LLM output parsing pipeline.

Provides a validated, machine-readable pathway from raw LLM responses to
finalized segments with guaranteed required fields.

Components
----------
LLMSegment / LLMExtractionResult
    Pydantic schemas that enforce all required fields and value constraints.

CharacterRegistry
    Persistent mapping from a speaker name to a stable ``character_id``.
    Identical names (case-insensitive) always resolve to the same ID
    within a processing session.

parse_llm_json
    Tolerant JSON extractor that strips code fences, applies deterministic
    repairs (smart-quotes, trailing commas), and falls back to snippet
    extraction before giving up.

post_process_segments
    Deterministic post-processor that:
    - drops empty / whitespace-only segments,
    - normalises text and segment type,
    - maps speaker_name -> persistent character_id via a registry,
    - inserts a Narrator/Unknown fallback when speaker is missing.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid type enum
# ---------------------------------------------------------------------------

CharacterType = Literal["dialogue", "thought", "narration"]

_VALID_TYPES: frozenset[str] = frozenset({"dialogue", "thought", "narration"})

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class LLMSegment(BaseModel):
    """A single extracted segment from LLM output.

    ``line_id`` and ``raw_text`` are required.  ``normalized_text`` defaults to
    ``raw_text`` when omitted.  ``speaker_name`` is nullable; the
    post-processor applies a deterministic fallback.
    """

    line_id: str
    raw_text: str
    normalized_text: str = ""
    speaker_name: Optional[str] = None
    speaker_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    character_type: CharacterType = "narration"
    voice_hint: Optional[str] = None

    @field_validator("normalized_text", mode="before")
    @classmethod
    def _strip_normalized(cls, v: Any) -> str:
        return str(v or "").strip()

    @field_validator("raw_text", mode="before")
    @classmethod
    def _coerce_raw_text(cls, v: Any) -> str:
        return str(v or "")

    @field_validator("speaker_name", mode="before")
    @classmethod
    def _strip_speaker_name(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        cleaned = str(v).strip()
        return cleaned if cleaned else None

    @field_validator("character_type", mode="before")
    @classmethod
    def _normalise_character_type(cls, v: Any) -> CharacterType:
        lowered = str(v or "").strip().lower()
        return lowered if lowered in _VALID_TYPES else "narration"  # type: ignore[return-value]

    def effective_text(self) -> str:
        """Return ``normalized_text`` if non-empty, otherwise ``raw_text``."""
        return self.normalized_text.strip() or self.raw_text.strip()


class LLMExtractionResult(BaseModel):
    """Top-level structured LLM extraction output."""

    segments: List[LLMSegment]


# ---------------------------------------------------------------------------
# Character Registry
# ---------------------------------------------------------------------------


class CharacterRegistry:
    """Persistent mapping from speaker name to a stable ``character_id``.

    Names are matched case-insensitively.  Each unique name that appears in a
    session receives exactly one ID, which is reused on subsequent calls.

    Example::

        registry = CharacterRegistry()
        info = registry.get_or_create("Alice")
        # {"character_id": "char_1", "display_name": "Alice"}

        info2 = registry.get_or_create("ALICE")
        assert info2["character_id"] == info["character_id"]  # same ID
    """

    def __init__(self) -> None:
        self._by_name: dict[str, dict[str, str]] = {}
        self._next_id: int = 1

    # -------------------------
    # Public API
    # -------------------------

    def get_or_create(self, speaker_name: str) -> dict[str, str]:
        """Return existing character info or create a new entry.

        Parameters
        ----------
        speaker_name:
            Display name for the speaker (will be normalised internally).

        Returns
        -------
        dict with ``character_id`` and ``display_name`` keys.
        """
        display = speaker_name.strip() if speaker_name else "Narrator"
        key = display.lower()
        if not key:
            key = "narrator"
            display = "Narrator"
        if key not in self._by_name:
            self._by_name[key] = {
                "character_id": f"char_{self._next_id}",
                "display_name": display,
            }
            self._next_id += 1
        return self._by_name[key]

    def all_characters(self) -> list[dict[str, str]]:
        """Return all registered characters in insertion order."""
        return list(self._by_name.values())

    def __len__(self) -> int:
        return len(self._by_name)


# ---------------------------------------------------------------------------
# JSON Parsing helpers
# ---------------------------------------------------------------------------


def _strip_code_fences(text: str) -> str:
    """Remove leading/trailing Markdown code fences from an LLM response."""
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_json_snippet(text: str) -> str:
    """Extract the first JSON object or array substring from *text*."""
    obj_start = text.find("{")
    arr_start = text.find("[")
    candidates = [i for i in (obj_start, arr_start) if i != -1]
    if not candidates:
        return text
    start = min(candidates)
    end = max(text.rfind("}"), text.rfind("]"))
    if end <= start:
        return text[start:]
    return text[start : end + 1]


def _deterministic_repair(text: str) -> str:
    """Apply common LLM-output fixups that produce invalid JSON.

    - Replaces curly/smart quotes with straight quotes.
    - Removes trailing commas before ``}`` or ``]``.
    """
    text = (
        text.replace("\u201c", '"')  # LEFT DOUBLE QUOTATION MARK
        .replace("\u201d", '"')  # RIGHT DOUBLE QUOTATION MARK
        .replace("\u2018", "'")  # LEFT SINGLE QUOTATION MARK
        .replace("\u2019", "'")  # RIGHT SINGLE QUOTATION MARK
    )
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def parse_llm_json(raw: Any) -> Any:
    """Robustly parse JSON from a raw LLM response.

    Resolution order
    ----------------
    1. Return *raw* unchanged if it is already a ``dict`` or ``list``.
    2. Strip Markdown code fences.
    3. Attempt ``json.loads`` directly.
    4. Apply deterministic repairs (smart quotes, trailing commas) and retry.
    5. Extract the first JSON object/array substring and retry.
    6. Raise ``ValueError`` with an actionable message on final failure.

    Parameters
    ----------
    raw:
        Raw LLM response — may be a string, dict, list, or ``None``.

    Returns
    -------
    Parsed Python object (dict or list).

    Raises
    ------
    ValueError
        When all repair strategies are exhausted without producing valid JSON.
    """
    if isinstance(raw, (dict, list)):
        return raw

    text = "" if raw is None else str(raw).strip()
    if not text:
        logger.warning("parse_llm_json: received empty LLM response")
        raise ValueError("LLM response is empty")

    text = _strip_code_fences(text)

    # Attempt 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: deterministic repairs then parse
    repaired = _deterministic_repair(text)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Attempt 3: extract first JSON snippet and parse
    snippet = _extract_json_snippet(repaired).strip()
    try:
        return json.loads(snippet)
    except json.JSONDecodeError as exc:
        logger.warning(
            "parse_llm_json: all repair strategies exhausted. "
            "Original length=%d, repaired length=%d, error=%s",
            len(str(raw)),
            len(snippet),
            exc,
        )
        raise ValueError(
            f"Unable to parse JSON from LLM response after all repairs: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Post-Processing Pipeline
# ---------------------------------------------------------------------------

_TRAILING_PUNCT = frozenset(".,!?;:")


def _clean_speaker(name: str) -> str:
    """Strip trailing punctuation from a speaker name."""
    name = name.strip()
    while name and name[-1] in _TRAILING_PUNCT:
        name = name[:-1].rstrip()
    return name


def post_process_segments(
    segments: list[dict[str, Any]],
    registry: CharacterRegistry,
) -> list[dict[str, Any]]:
    """Post-process raw LLM segment dicts into finalized output.

    For each segment:

    1. Resolve the display text (``normalized_text`` > ``text`` > ``raw_text``).
    2. Drop the segment if the resolved text is empty or whitespace-only.
    3. Normalise ``segment_type`` to the controlled enum
       (``dialogue`` | ``thought`` | ``narration``); default ``narration``.
    4. Normalise ``speaker``:
       - strip trailing punctuation,
       - if empty: use ``"Narrator"`` for non-dialogue, ``"Unknown"`` for dialogue.
    5. Resolve ``character_id`` via *registry* (creates a new entry if needed).

    Parameters
    ----------
    segments:
        Raw dicts from the LLM or segmenter.  Accepted field aliases:

        - text / raw_text / normalized_text
        - character_type / type
        - speaker_name / speaker
        - line_id / paragraph_id
        - voice_hint

    registry:
        A ``CharacterRegistry`` instance shared across the processing session
        to ensure consistent character IDs.

    Returns
    -------
    A list of dicts with guaranteed fields:
    ``line_id``, ``text``, ``segment_type``, ``speaker``,
    ``character_id``, ``voice_hint``.
    """
    output: list[dict[str, Any]] = []

    for seg in segments:
        # Resolve text, preferring already-normalised fields
        text = (
            str(seg.get("normalized_text") or "").strip()
            or str(seg.get("text") or "").strip()
            or str(seg.get("raw_text") or "").strip()
        )
        if not text:
            logger.debug(
                "post_process_segments: dropping empty segment line_id=%r",
                seg.get("line_id") or seg.get("paragraph_id"),
            )
            continue

        # Normalise segment type
        raw_type = str(seg.get("character_type") or seg.get("type") or "").strip().lower()
        seg_type = raw_type if raw_type in _VALID_TYPES else "narration"

        # Normalise speaker name
        raw_speaker = str(seg.get("speaker_name") or seg.get("speaker") or "").strip()
        speaker = _clean_speaker(raw_speaker)
        if not speaker or speaker.lower() in {"", "none"}:
            speaker = "Narrator" if seg_type != "dialogue" else "Unknown"

        char_info = registry.get_or_create(speaker)

        output.append(
            {
                "line_id": str(seg.get("line_id") or seg.get("paragraph_id") or ""),
                "text": text,
                "segment_type": seg_type,
                "speaker": speaker,
                "character_id": char_info["character_id"],
                "voice_hint": seg.get("voice_hint"),
            }
        )

    return output


def validate_and_post_process(
    raw: Any,
    registry: CharacterRegistry,
    *,
    repair_callback: Any = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Parse, validate, and post-process a raw LLM response end-to-end.

    Combines ``parse_llm_json``, Pydantic schema validation, and
    ``post_process_segments`` in a single convenience function.

    Parameters
    ----------
    raw:
        Raw LLM response (string, dict, list, or None).
    registry:
        CharacterRegistry for persistent speaker mapping.
    repair_callback:
        Optional callable ``(raw_response) -> Any`` invoked when the initial
        parse or schema validation fails.  If it returns a non-None value,
        that value is used as a second parse attempt.

    Returns
    -------
    (finalized_segments, success)
        *finalized_segments* is the list from ``post_process_segments``.
        *success* is ``True`` when the original (or repaired) response passed
        schema validation without falling back to heuristics.
    """
    from pydantic import ValidationError  # local import to avoid top-level dep issues

    def _try_parse_and_validate(data: Any) -> list[dict[str, Any]] | None:
        try:
            parsed = parse_llm_json(data)
        except ValueError as exc:
            logger.warning("validate_and_post_process: JSON parse failed: %s", exc)
            return None

        # Accept either {"segments": [...]} envelope or bare array
        if isinstance(parsed, dict) and "segments" in parsed:
            parsed = parsed["segments"]

        if not isinstance(parsed, list):
            logger.warning(
                "validate_and_post_process: expected list, got %s", type(parsed).__name__
            )
            return None

        # Pydantic schema validation per segment
        validated: list[dict[str, Any]] = []
        for i, item in enumerate(parsed):
            if not isinstance(item, dict):
                logger.warning("validate_and_post_process: item %d is not a dict", i)
                continue
            try:
                seg = LLMSegment.model_validate(item)
                validated.append(seg.model_dump())
            except ValidationError as exc:
                logger.warning(
                    "validate_and_post_process: segment %d failed schema validation: %s",
                    i,
                    exc,
                )
        return validated if validated else None

    result = _try_parse_and_validate(raw)

    if result is None and repair_callback is not None:
        logger.info(
            "validate_and_post_process: primary parse failed; invoking repair_callback"
        )
        try:
            repaired = repair_callback(raw)
            result = _try_parse_and_validate(repaired)
        except Exception as exc:
            logger.warning(
                "validate_and_post_process: repair_callback raised: %s", exc
            )

    if result is None:
        logger.warning(
            "validate_and_post_process: all attempts failed; returning empty segments"
        )
        return [], False

    finalized = post_process_segments(result, registry)
    return finalized, True
