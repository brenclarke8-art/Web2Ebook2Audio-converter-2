from __future__ import annotations

import traceback
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Signal, QThread

def _make_tts_backend(settings, output_dir: Optional[str] = None):
    """Return the remote TTS client (backend-only mode)."""
    from ebook_app.services.tts_client import TTSClient

    effective_output_dir = output_dir or settings.output_dir
    if settings.tts_backend_mode != "remote":
        settings.tts_backend_mode = "remote"
    return TTSClient(
        output_dir=effective_output_dir,
        base_url=settings.tts_backend_url,
    )


class TTSThread(QThread):
    progress = Signal(str)
    finished = Signal(Path)
    error = Signal(str)

    def __init__(
        self,
        engine,
        *,
        text: Optional[str] = None,
        output_filename: Optional[str] = None,
        voice: str = "af_heart",
        lang_code: str = "a",
        speed: float = 1.0,
        dialogue_segments: Optional[List] = None,
        voice_mappings: Optional[Dict[str, str]] = None,
        multi_voice: bool = False,
    ):
        super().__init__()
        self.engine = engine
        self.text = text
        self.output_filename = output_filename
        self.voice = voice
        self.lang_code = lang_code
        self.speed = speed
        self.dialogue_segments = dialogue_segments or []
        self.voice_mappings = voice_mappings or {}
        self.multi_voice = multi_voice

    def _progress_cb(self, msg: str) -> None:
        self.progress.emit(msg)

    def run(self) -> None:
        try:
            if self.multi_voice:
                path = self.engine.generate_multi_voice_audio(
                    self.dialogue_segments,
                    self.output_filename,
                    self.voice_mappings,
                    lang_code=self.lang_code,
                    speed=self.speed,
                    progress_callback=self._progress_cb,
                )
            else:
                path = self.engine.generate_audio(
                    self.text,
                    self.output_filename,
                    voice=self.voice,
                    lang_code=self.lang_code,
                    speed=self.speed,
                    progress_callback=self._progress_cb,
                )
            self.finished.emit(path)
        except Exception as exc:
            tb = traceback.format_exc()
            self.error.emit(f"{exc}\n\n{tb}")


class TTSService(QObject):
    progress_changed = Signal(str)
    audio_ready = Signal(Path)
    error_occurred = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.engine = _make_tts_backend(settings)
        self._current_thread = None

    def _connect_thread(self, thread: TTSThread) -> None:
        thread.progress.connect(self.progress_changed)
        thread.finished.connect(self.audio_ready)
        thread.error.connect(self.error_occurred)
        thread.finished.connect(thread.deleteLater)
        thread.error.connect(thread.deleteLater)

    def generate_single_voice(
        self,
        text: str,
        output_filename: str,
        *,
        voice: str = "af_heart",
        lang_code: str = "a",
        speed: float = 1.0,
    ) -> None:
        if self._current_thread and self._current_thread.isRunning():
            return

        thread = TTSThread(
            self.engine,
            text=text,
            output_filename=output_filename,
            voice=voice,
            lang_code=lang_code,
            speed=speed,
            multi_voice=False,
        )
        self._current_thread = thread
        self._connect_thread(thread)
        thread.start()

    def generate_multi_voice(
        self,
        dialogue_segments: List,
        output_filename: str,
        voice_mappings: Dict[str, str],
        *,
        lang_code: str = "a",
        speed: float = 1.0,
    ) -> None:
        if self._current_thread and self._current_thread.isRunning():
            return

        thread = TTSThread(
            self.engine,
            output_filename=output_filename,
            dialogue_segments=dialogue_segments,
            voice_mappings=voice_mappings,
            lang_code=lang_code,
            speed=speed,
            multi_voice=True,
        )
        self._current_thread = thread
        self._connect_thread(thread)
        thread.start()

class TTSBatchThread(QThread):
    progress = Signal(str)
    batch_finished = Signal(list)   # list of output paths
    error = Signal(str)

    def __init__(self, engine, chapters, filenames, voice, lang_code, speed):
        super().__init__()
        self.engine = engine
        self.chapters = chapters
        self.filenames = filenames
        self.voice = voice
        self.lang_code = lang_code
        self.speed = speed

    def _progress(self, msg):
        self.progress.emit(msg)

    def run(self):
        try:
            outputs = []
            total = len(self.chapters)

            for i, (text, filename) in enumerate(zip(self.chapters, self.filenames)):
                self._progress(f"Generating chapter {i+1}/{total}...")
                path = self.engine.generate_audio(
                    text=text,
                    output_filename=filename,
                    voice=self.voice,
                    lang_code=self.lang_code,
                    speed=self.speed,
                    progress_callback=self._progress
                )
                outputs.append(str(path))

            self.batch_finished.emit(outputs)

        except Exception as e:
            self.error.emit(str(e))

def generate_batch(self, chapters, filenames, *, voice, lang_code="a", speed=1.0):
    if self._current_thread and self._current_thread.isRunning():
        return

    thread = TTSBatchThread(
        self.engine,
        chapters,
        filenames,
        voice,
        lang_code,
        speed
    )

    self._current_thread = thread
    self._connect_thread(thread)

    # Connect batch-specific signal
    thread.batch_finished.connect(self.audio_ready)

    thread.start()
