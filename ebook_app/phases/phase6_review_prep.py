# ebook_app/phases/phase6_review_prep.py
"""Phase 6 — Review and Audio Generation Prep.

Assembles the final reviewed segment list by:
  1. Applying any manual overrides from the review UI.
  2. Routing voices to each segment via VoiceRouter + CharacterDatabase.
  3. Marking segments that still need human attention (low confidence).

This phase is always presented to the user in manual/semi_auto mode for
confirmation before proceeding to audio generation.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from ebook_app.phases.phase_base import PhaseBase, PhaseResult

logger = logging.getLogger(__name__)


class Phase6ReviewPrep(PhaseBase):
    """Phase 6: apply overrides, route voices, prepare final segment list."""

    def run(self, chapter_id: str, **kwargs) -> PhaseResult:
        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        segments: List[dict] = kwargs.get("segments", [])
        character_db: Any = kwargs.get("character_db")
        overrides: Dict[str, dict] = kwargs.get("overrides", {})
        work_dir: Any = kwargs.get("work_dir")

        if not segments:
            return PhaseResult.error_result("No segments provided for review prep.")

        self._emit_progress(10)

        try:
            from ebook_app.tts.voice_router import VoiceRouter

            voice_router = VoiceRouter(
                narrator_voice=self.settings.get("narrator_voice", "af_heart"),
                default_male_voice=self.settings.get("default_male_voice", "am_adam"),
                default_female_voice=self.settings.get("default_female_voice", "af_bella"),
            )
        except Exception as exc:
            logger.error("[Phase6] VoiceRouter init failed: %s", exc)
            return PhaseResult.error_result(f"VoiceRouter init failed: {exc}")

        self._emit_progress(20)

        final_segments: List[dict] = []
        needs_review_count = 0
        conf_threshold = 0.8

        for seg in segments:
            if self.is_cancelled():
                return PhaseResult.cancelled_result()

            seg_copy = dict(seg)

            # Apply manual overrides from the review UI (keyed by segment_id)
            seg_id = seg_copy.get("segment_id", "")
            if seg_id in overrides:
                seg_copy.update(overrides[seg_id])

            # Route voice
            if character_db is not None:
                voice = voice_router.get_voice_for_segment(seg_copy, character_db)
                seg_copy["voice"] = voice

            # Flag low-confidence segments
            conf = float(seg_copy.get("speaker_confidence", 1.0))
            if conf < conf_threshold:
                seg_copy["needs_review"] = True
                needs_review_count += 1
            else:
                seg_copy.setdefault("needs_review", False)

            final_segments.append(seg_copy)

        self._emit_progress(80)

        # Persist to work dir
        if work_dir:
            work_dir = Path(work_dir)
            work_dir.mkdir(parents=True, exist_ok=True)
            out = work_dir / f"{chapter_id}_final.json"
            out.write_text(
                json.dumps({"chapter_id": chapter_id, "segments": final_segments},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        self._emit_progress(100)

        summary = (
            f"Final segments: {len(final_segments)}\n"
            f"Segments flagged for review: {needs_review_count}"
        )

        return PhaseResult(
            success=True,
            output_text=summary,
            data={
                "segments": final_segments,
                "needs_review_count": needs_review_count,
            },
        )
