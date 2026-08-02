# ebook_app/phases/phase5b_classification.py
"""Phase 5b — LLM Classification.

Uses Pass-2 (LLM-based) classification to assign to every segment:
  - type        (dialogue / thought / narration)
  - speaker     (character name or "narrator")
  - gender      (male / female / unknown)
  - speaker_confidence
  - gender_confidence
  - character_confidence
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, List, Optional

from ebook_app.phases.phase_base import PhaseBase, PhaseResult

logger = logging.getLogger(__name__)


class Phase5bClassification(PhaseBase):
    """Phase 5b: LLM-based segment classification."""

    def run(self, chapter_id: str, **kwargs) -> PhaseResult:
        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        segments: List[dict] = kwargs.get("segments", [])
        work_dir: Any = kwargs.get("work_dir")
        conversation_callback: Optional[Callable] = kwargs.get("conversation_callback")

        if not segments:
            return PhaseResult.error_result("No segments provided for classification.")

        self._emit_progress(5)

        try:
            from ebook_app.text.identify.type_classifier import LLMClient, Pass2Classifier

            llm_client = LLMClient(
                base_url=self.settings.get("llm_url", ""),
                model=self.settings.get("llm_model", ""),
                timeout=int(self.settings.get("llm_timeout", 300)),
                retries=int(self.settings.get("llm_retries", 1)),
                provider=self.settings.get("llm_provider", "ollama_local"),
                api_key=self.settings.get("llm_api_key", ""),
                on_conversation=conversation_callback,
            )

            batch_size = int(self.settings.get("llm_batch_size", 20))
            classifier = Pass2Classifier(llm_client, batch_size=batch_size)
        except Exception as exc:
            logger.error("[Phase5b] Could not initialise LLM client: %s", exc, exc_info=True)
            return PhaseResult.error_result(f"LLM setup failed: {exc}")

        self._emit_progress(15)

        total = len(segments)
        classified: List[dict] = []

        try:
            for i, seg in enumerate(segments):
                if self.is_cancelled():
                    return PhaseResult.cancelled_result()

                results = classifier.classify_batch([seg])
                classified.extend(results if results else [seg])
                self._emit_progress(15 + int(80 * (i + 1) / total))

        except Exception as exc:
            logger.error("[Phase5b] Classification failed: %s", exc, exc_info=True)
            return PhaseResult.error_result(f"Classification failed: {exc}")

        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        # Persist to work dir
        if work_dir:
            work_dir = Path(work_dir)
            work_dir.mkdir(parents=True, exist_ok=True)
            out = work_dir / f"{chapter_id}_pass2.json"
            out.write_text(
                json.dumps({"chapter_id": chapter_id, "segments": classified},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        self._emit_progress(100)

        high_conf = sum(
            1 for s in classified
            if float(s.get("speaker_confidence", 0)) >= 0.8
        )
        summary = (
            f"Classified segments: {len(classified)}\n"
            f"High-confidence speaker assignments: {high_conf}/{len(classified)}"
        )

        return PhaseResult(
            success=True,
            output_text=summary,
            data={"segments": classified, "segment_count": len(classified)},
        )
