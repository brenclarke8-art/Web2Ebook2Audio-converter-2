# ebook_app/phases/phase4_segmentation.py
"""Phase 4 — Text Segmentation.

Splits the cleaned/translated chapter text into labelled segments:
dialogue, thought, and narration.  Uses the deterministic Pass-1 extractor
(no LLM).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, List

from ebook_app.phases.phase_base import PhaseBase, PhaseResult

logger = logging.getLogger(__name__)


class Phase4Segmentation(PhaseBase):
    """Phase 4: split text into segments (dialogue / thought / narration)."""

    def run(self, chapter_id: str, **kwargs) -> PhaseResult:
        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        text: str = kwargs.get("text", "")
        work_dir: Any = kwargs.get("work_dir")

        if not text.strip():
            return PhaseResult.error_result("No text provided for segmentation.")

        self._emit_progress(10)

        try:
            from ebook_app.text.identify.role_tagger import Pass1Extractor

            extractor = Pass1Extractor()
            segments: List[dict] = extractor.extract(text, chapter_id)
        except Exception as exc:
            logger.error("[Phase4] Segmentation failed: %s", exc, exc_info=True)
            return PhaseResult.error_result(f"Segmentation failed: {exc}")

        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        self._emit_progress(80)

        # Persist to work dir
        if work_dir:
            work_dir = Path(work_dir)
            work_dir.mkdir(parents=True, exist_ok=True)
            out_path = work_dir / f"{chapter_id}_pass1.json"
            out_path.write_text(
                json.dumps({"chapter_id": chapter_id, "segments": segments},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        self._emit_progress(100)

        # Build a readable summary for the diff panel
        dialogue_count = sum(1 for s in segments if s.get("is_dialogue_candidate"))
        summary = (
            f"Total segments: {len(segments)}\n"
            f"Dialogue candidates: {dialogue_count}\n"
            f"Narration segments: {len(segments) - dialogue_count}"
        )

        return PhaseResult(
            success=True,
            output_text=summary,
            data={"segments": segments, "segment_count": len(segments)},
        )
