"""
ebook_app.services.story_context_service

Experimental chapter-to-chapter story context service.

Maintains a rolling story state that can be injected into LLM prompts to
give the model continuity across chapter boundaries.  The persisted context
is intentionally bounded to a single short paragraph so token usage stays
manageable.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ebook_app.services.llm_client import OllamaChatClient

logger = logging.getLogger(__name__)

# ── System prompt used when generating / updating the story context ──────────

_STORY_CONTEXT_SYSTEM_PROMPT = """\
You are a concise story-continuity assistant for a novel processing pipeline.
Given a chapter of text (and optionally the prior story state), output a STRICT JSON
object with exactly two keys:

1. "summary"          – One paragraph, max 100 words.  Capture: active characters,
                        recent events, unresolved threads, current location/time, and
                        key continuity facts.  Write in present tense, third person.
2. "active_characters" – A JSON list of strings: only explicitly named characters who
                        appear in THIS chapter.  No unnamed roles ("the guard").

Rules:
- Return ONLY valid JSON — no prose, no markdown fences, no extra keys.
- summary MUST be one paragraph of at most 100 words.
- active_characters MUST list only characters explicitly named in the chapter text.

JSON FORMAT:
{
  "summary": "string",
  "active_characters": ["Name1", "Name2"]
}
"""


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class StoryContext:
    """Persistent rolling story context stored alongside the book project."""

    summary: str = ""
    active_characters: list[str] = field(default_factory=list)
    last_chapter_id: str = ""

    # ------------------------------------------------------------------
    # Prompt injection
    # ------------------------------------------------------------------

    def to_prompt_block(self) -> str:
        """Return a formatted block for injection at the top of an LLM prompt.

        Returns an empty string when there is no context yet (first chapter).
        """
        if not self.summary.strip():
            return ""
        lines = [
            "STORY CONTEXT (from prior chapters — use for continuity only):",
        ]
        if self.active_characters:
            lines.append(f"Active characters: {', '.join(self.active_characters)}")
        lines.append(f"Recent context: {self.summary}")
        lines.append(
            "Use this context to maintain continuity in character attribution and "
            "story awareness.  Do NOT invent new details from this context."
        )
        return "\n".join(lines)

    def is_empty(self) -> bool:
        return not self.summary.strip()

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoryContext:
        raw_active = data.get("active_characters", [])
        if not isinstance(raw_active, list):
            raw_active = []
        return cls(
            summary=str(data.get("summary", "")),
            active_characters=[str(c) for c in raw_active if str(c).strip()],
            last_chapter_id=str(data.get("last_chapter_id", "")),
        )

    # ------------------------------------------------------------------
    # File persistence
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> StoryContext:
        """Load from *path*; return an empty context if the file is absent or corrupt."""
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls.from_dict(data)
        except Exception:
            logger.warning("Failed to load story context from %s — starting fresh.", path)
            return cls()

    def save(self, path: Path) -> None:
        """Persist the context to *path*."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            logger.error("Failed to save story context to %s", path, exc_info=True)


# ── Service ───────────────────────────────────────────────────────────────────

# Maximum characters of chapter text forwarded to the context LLM call.
# Keeps token usage bounded while giving the model enough material.
_MAX_CHAPTER_CHARS_FOR_CONTEXT = 3000

# Hard cap on the persisted summary string (roughly one paragraph).
_MAX_SUMMARY_CHARS = 600


class StoryContextService:
    """Generate and update rolling story context via the LLM after each chapter."""

    def __init__(self, *, client: OllamaChatClient) -> None:
        self.client = client

    def update_from_chapter(
        self,
        *,
        chapter_text: str,
        chapter_id: str,
        prior_context: StoryContext | None = None,
    ) -> StoryContext:
        """Ask the LLM to produce a new story context from *chapter_text*.

        Falls back to *prior_context* (or an empty context) if the LLM call
        fails or returns unusable output.
        """
        fallback = prior_context or StoryContext()

        # Truncate chapter text to stay within reasonable token limits
        truncated = chapter_text[:_MAX_CHAPTER_CHARS_FOR_CONTEXT]
        if len(chapter_text) > _MAX_CHAPTER_CHARS_FOR_CONTEXT:
            truncated += "…"

        # Build the user message
        parts: list[str] = []
        if prior_context and not prior_context.is_empty():
            parts.append(f"PRIOR STORY STATE:\n{prior_context.summary}")
            if prior_context.active_characters:
                parts.append(
                    "Prior active characters: "
                    + ", ".join(prior_context.active_characters)
                )
        parts.append(f"CHAPTER TEXT:\n{truncated}")
        user_text = "\n\n".join(parts)

        try:
            raw = self.client.ask_json(
                system=_STORY_CONTEXT_SYSTEM_PROMPT,
                user=user_text,
                chapter_id=f"{chapter_id}_ctx",
            )
        except Exception:
            logger.warning(
                "Story context LLM call failed for %s — keeping prior context.",
                chapter_id,
                exc_info=True,
            )
            return fallback

        if not isinstance(raw, dict):
            logger.warning("Story context LLM returned non-dict for %s.", chapter_id)
            return fallback

        summary = str(raw.get("summary", "")).strip()
        if not summary:
            logger.warning(
                "Story context LLM returned empty summary for %s.", chapter_id
            )
            return fallback

        # Cap summary length
        if len(summary) > _MAX_SUMMARY_CHARS:
            capped = summary[:_MAX_SUMMARY_CHARS]
            word_boundary = capped.rsplit(" ", 1)[0].strip()
            summary = word_boundary if word_boundary else capped
            if len(summary) < _MAX_SUMMARY_CHARS:
                summary = f"{summary}…"

        raw_active_characters = raw.get("active_characters", [])
        if not isinstance(raw_active_characters, list):
            raw_active_characters = []
        active_characters = [str(c).strip() for c in raw_active_characters if str(c).strip()]

        return StoryContext(
            summary=summary,
            active_characters=active_characters,
            last_chapter_id=chapter_id,
        )
