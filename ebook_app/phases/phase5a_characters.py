# ebook_app/phases/phase5a_characters.py
"""Phase 5a — Character Identification and Storage.

Scans the segments from Phase 4, extracts candidate character names using
Pass-1 heuristics and the character-DB updater, and merges them into the
project's CharacterDatabase.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, List

from ebook_app.phases.phase_base import PhaseBase, PhaseResult

logger = logging.getLogger(__name__)


class Phase5aCharacters(PhaseBase):
    """Phase 5a: discover characters and update the character database."""

    def run(self, chapter_id: str, **kwargs) -> PhaseResult:
        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        segments: List[dict] = kwargs.get("segments", [])
        character_db: Any = kwargs.get("character_db")
        work_dir: Any = kwargs.get("work_dir")

        if not segments:
            return PhaseResult.error_result("No segments provided for character identification.")

        self._emit_progress(10)

        try:
            from ebook_app.text.identify.character_db_updater import CharacterDBUpdater

            updater = CharacterDBUpdater(character_db=character_db)
            discovered = updater.update_from_segments(segments)
        except Exception as exc:
            logger.error("[Phase5a] Character identification failed: %s", exc, exc_info=True)
            return PhaseResult.error_result(f"Character identification failed: {exc}")

        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        self._emit_progress(80)

        # Save updated character DB
        if work_dir and character_db is not None:
            work_dir = Path(work_dir)
            work_dir.mkdir(parents=True, exist_ok=True)
            try:
                character_db.save()
            except Exception as exc:
                logger.warning("[Phase5a] Could not save character DB: %s", exc)

        self._emit_progress(100)

        char_list = character_db.list_characters() if character_db else []
        summary_lines = [f"  • {c.name} ({c.gender})" for c in char_list[:20]]
        summary = (
            f"Characters in database: {len(char_list)}\n"
            + ("\n".join(summary_lines) if summary_lines else "(none)")
        )

        return PhaseResult(
            success=True,
            output_text=summary,
            data={
                "character_count": len(char_list),
                "characters": [c.to_dict() for c in char_list],
                "newly_discovered": len(discovered) if discovered else 0,
            },
        )
