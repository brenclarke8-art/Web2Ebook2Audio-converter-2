# ebook_app/phases/phase3_translation.py
"""Phase 3 — Optional Translation.

Translates the cleaned text from Phase 2 into the target language using
the configured translation provider (LLM, DeepL, or Google).
If translation is disabled in settings this phase is a no-op.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ebook_app.phases.phase_base import PhaseBase, PhaseResult

logger = logging.getLogger(__name__)


class Phase3Translation(PhaseBase):
    """Phase 3: translate cleaned text (optional)."""

    def run(self, chapter_id: str, **kwargs) -> PhaseResult:
        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        text: str = kwargs.get("text", "")
        work_dir: Any = kwargs.get("work_dir")

        translation_enabled: bool = bool(
            self.settings.get("translation_enabled", False)
        )

        if not translation_enabled:
            logger.debug("[Phase3] Translation disabled — passing text through unchanged.")
            self._emit_progress(100)
            return PhaseResult(
                success=True,
                output_text=text,
                data={"translated_text": text, "skipped": True},
            )

        if not text.strip():
            return PhaseResult.error_result("No text provided for translation.")

        self._emit_progress(10)

        target_lang: str = self.settings.get("translation_target_language", "en")
        llm_url: str = self.settings.get("llm_url", "")
        llm_model: str = self.settings.get("llm_model", "")

        try:
            from ebook_app.text.translate.translator import Translator

            translator = Translator(
                provider="llm",
                target_language=target_lang,
                llm_url=llm_url,
                llm_model=llm_model,
                timeout=int(self.settings.get("llm_timeout", 300)),
            )

            self._emit_progress(30)

            if self.is_cancelled():
                return PhaseResult.cancelled_result()

            translated = translator.translate(text)

            self._emit_progress(90)

        except Exception as exc:
            logger.error("[Phase3] Translation failed: %s", exc, exc_info=True)
            return PhaseResult.error_result(f"Translation failed: {exc}")

        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        # Persist to work dir
        if work_dir:
            work_dir = Path(work_dir)
            work_dir.mkdir(parents=True, exist_ok=True)
            (work_dir / f"{chapter_id}_translated.txt").write_text(
                translated, encoding="utf-8"
            )

        self._emit_progress(100)

        return PhaseResult(
            success=True,
            output_text=translated,
            data={"translated_text": translated, "target_language": target_lang},
        )
