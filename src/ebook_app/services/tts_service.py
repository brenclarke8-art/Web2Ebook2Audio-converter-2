# src/ebook_app/services/tts_service.py
"""Threaded TTS synthesis service."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ebook_app.models.tts_engine_cli import TTSEngineCLI


class TTSService(QThread):
    """QThread-based service that synthesises audio for all chapters.

    Signals:
        progress (int): 0–100 as chapters are synthesised.
        success (list[str]): WAV file paths on completion.
        error (str): Error message on failure.
    """

    progress: Signal = Signal(int)
    success: Signal = Signal(list)
    error: Signal = Signal(str)

    def __init__(
        self,
        chapter_dir: str,
        output_dir: str,
        voice: str,
        speed: float,
        cli_path: str,
    ) -> None:
        super().__init__()
        self.chapter_dir = chapter_dir
        self.output_dir = output_dir
        self.voice = voice
        self.speed = speed
        self._engine = TTSEngineCLI(cli_path=cli_path)

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Synthesise audio for all chapters.

        TODO: scan chapter_dir for .txt files, call self._engine.synthesise()
        per chapter, collect WAV paths, and emit progress.
        """
        try:
            self.progress.emit(0)
            wav_paths = self._batch_synthesise()
            self.progress.emit(100)
            self.success.emit(wav_paths)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))

    # ------------------------------------------------------------------
    # Placeholder methods
    # ------------------------------------------------------------------

    def _batch_synthesise(self) -> list[str]:
        """Iterate chapter files and synthesise WAV audio for each.

        TODO: implement real batch synthesis.
        """
        return []
