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
class CharacterMemoryEntry:
    """Compact per-character record stored in the rolling story context.

    Only the three fields required for continuity are kept; full descriptions
    and aliases are intentionally omitted to limit token growth.
    """

    name: str
    gender: str = "unknown"
    role: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "gender": self.gender, "role": self.role}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterMemoryEntry:
        return cls(
            name=str(data.get("name", "")).strip(),
            gender=str(data.get("gender", "unknown")).strip().lower(),
            role=str(data.get("role", "")).strip(),
        )


@dataclass
class StoryContext:
    """Persistent rolling story context stored alongside the book project."""

    summary: str = ""
    active_characters: list[str] = field(default_factory=list)
    last_chapter_id: str = ""
    # Compressed character memory: only name / gender / role per character.
    character_memory: list[CharacterMemoryEntry] = field(default_factory=list)

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
    # Character memory helpers
    # ------------------------------------------------------------------

    def get_character_memory_dicts(self) -> list[dict[str, Any]]:
        """Return character memory as a list of plain dicts (name/gender/role)."""
        return [entry.to_dict() for entry in self.character_memory]

    def update_character_memory(self, characters: list[dict[str, Any]]) -> None:
        """Merge *characters* into the compressed character memory.

        Each entry in *characters* should have at minimum a ``"name"`` key and
        optionally ``"gender"`` and ``"role"`` keys.  Only these three fields
        are stored.  Existing entries are updated; new ones are appended.
        """
        existing: dict[str, CharacterMemoryEntry] = {
            entry.name.lower(): entry for entry in self.character_memory
        }
        for char in characters:
            if not isinstance(char, dict):
                continue
            name = str(char.get("name", "")).strip()
            if not name:
                continue
            gender = str(char.get("gender", "unknown")).strip().lower()
            if gender not in {"male", "female"}:
                gender = "unknown"
            role = str(char.get("role", "")).strip()
            key = name.lower()
            if key in existing:
                entry = existing[key]
                if entry.gender == "unknown" and gender != "unknown":
                    entry.gender = gender
                if not entry.role and role:
                    entry.role = role
            else:
                existing[key] = CharacterMemoryEntry(name=name, gender=gender, role=role)
        self.character_memory = list(existing.values())

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["character_memory"] = [e.to_dict() for e in self.character_memory]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoryContext:
        raw_active = data.get("active_characters", [])
        if not isinstance(raw_active, list):
            raw_active = []
        raw_memory = data.get("character_memory", [])
        if not isinstance(raw_memory, list):
            raw_memory = []
        character_memory = [
            CharacterMemoryEntry.from_dict(item)
            for item in raw_memory
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        ]
        return cls(
            summary=str(data.get("summary", "")),
            active_characters=[str(c) for c in raw_active if str(c).strip()],
            last_chapter_id=str(data.get("last_chapter_id", "")),
            character_memory=character_memory,
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
        detected_characters: list[dict[str, Any]] | None = None,
    ) -> StoryContext:
        """Ask the LLM to produce a new story context from *chapter_text*.

        If *detected_characters* is provided (a list of dicts with at least
        ``"name"`` and optionally ``"gender"`` / ``"role"`` keys), the
        character memory is updated from that list **without** making an extra
        LLM call — this is the preferred fast path when dialogue parsing has
        already extracted character information for the chapter.

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
            word_boundary = capped.rsplit(" ", 1)[0].strip() if " " in capped else ""
            if word_boundary:
                summary = f"{word_boundary}…"
            else:
                summary = f"{capped[:-1]}…"

        raw_active_characters = raw.get("active_characters", [])
        if not isinstance(raw_active_characters, list):
            raw_active_characters = []
        active_characters = [str(c).strip() for c in raw_active_characters if str(c).strip()]

        new_context = StoryContext(
            summary=summary,
            active_characters=active_characters,
            last_chapter_id=chapter_id,
            character_memory=list(fallback.character_memory),
        )

        # Update character memory from detected characters (fast path) or
        # from active_characters returned by the context LLM (fallback).
        if detected_characters:
            new_context.update_character_memory(detected_characters)
        elif active_characters:
            new_context.update_character_memory(
                [{"name": name} for name in active_characters]
            )

        return new_context
