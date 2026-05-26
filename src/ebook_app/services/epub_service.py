# src/ebook_app/services/epub_service.py
"""Threaded EPUB export service."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ebook_app.models.epub_builder import EpubBuilder


class EPUBService(QThread):
    """QThread-based service for packaging the final EPUB3 file.

    Signals:
        progress (int): 0–100 during export.
        success (str): Path to the generated .epub file.
        error (str): Error message on failure.
    """

    progress: Signal = Signal(int)
    success: Signal = Signal(str)
    error: Signal = Signal(str)

    def __init__(
        self,
        chapter_dir: str,
        audio_dir: str,
        output_path: str,
        title: str = "Untitled",
        author: str = "Unknown",
        language: str = "en",
    ) -> None:
        super().__init__()
        self.chapter_dir = chapter_dir
        self.audio_dir = audio_dir
        self.output_path = output_path
        self.title = title
        self.author = author
        self.language = language
        self._builder = EpubBuilder()

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Build the EPUB3 package and write it to output_path.

        TODO: load chapters + audio, generate XHTML, build SMIL, package EPUB.
        """
        try:
            self.progress.emit(0)
            epub_path = self._builder.build(
                chapter_dir=self.chapter_dir,
                audio_dir=self.audio_dir,
                output_path=self.output_path,
                title=self.title,
                author=self.author,
                language=self.language,
            )
            self.progress.emit(100)
            self.success.emit(epub_path)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
