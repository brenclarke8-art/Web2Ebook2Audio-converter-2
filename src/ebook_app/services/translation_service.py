# src/ebook_app/services/translation_service.py
"""Threaded translation service."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class TranslationService(QThread):
    """QThread-based service for batch-translating chapter files.

    Signals:
        progress (int): 0–100 as chapters are translated.
        success (list[str]): Translated file paths on completion.
        error (str): Error message on failure.
    """

    progress: Signal = Signal(int)
    success: Signal = Signal(list)
    error: Signal = Signal(str)

    def __init__(self, chapter_dir: str, provider: str, target_lang: str) -> None:
        super().__init__()
        self.chapter_dir = chapter_dir
        self.provider = provider
        self.target_lang = target_lang

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Translate all chapter files found in chapter_dir.

        TODO: iterate chapter .txt files, send each to the chosen provider,
        save translated output, and emit progress.
        """
        try:
            self.progress.emit(0)
            translated = self._translate_all()
            self.progress.emit(100)
            self.success.emit(translated)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))

    # ------------------------------------------------------------------
    # Placeholder methods
    # ------------------------------------------------------------------

    def _translate_all(self) -> list[str]:
        """Translate every chapter file and return translated file paths.

        TODO: use deep_translator (or the chosen provider API) per chapter.
        """
        return []
