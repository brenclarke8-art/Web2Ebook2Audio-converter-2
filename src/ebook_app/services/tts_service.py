from __future__ import annotations

import traceback
from pathlib import Path
from typing import Dict, List, Optional, Any

from PySide6.QtCore import QObject, Signal, QThread


def _make_tts_backend(settings, output_dir: Optional[str] = None):
    """Return the remote TTS client (backend-only mode)."""
    from ebook_app.services.tts_client import TTSClient

    effective_output_dir = output_dir or settings.output_dir
    return TTSClient(
        output_dir=effective_output_dir,
        base_url=settings.tts_backend_url,
    )


class TTSThread(QThread):
    progress = Signal(str)
    finished = Signal(Path)  # single/combined audio path
    multi_audio_ready = Signal(Path, list, list, dict)  # combined_path, segment_paths, segment_timing, resolved_voices
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
        return_segments: str = "combined",  # "combined" | "segments" | "both"
        transition: str = "silence",        # "silence" | "crossfade" | "none"
        batch_mode: str = "single",         # "single" | "batch"
        debug: bool = False,
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
        self.return_segments = return_segments
        self.transition = transition
        self.batch_mode = batch_mode
        self.debug = debug

    def _progress_cb(self, msg: str) -> None:
        self.progress.emit(msg)

    def run(self) -> None:
        try:
            if self.multi_voice:
                # New-style multi-voice API: may return a dict with rich metadata
                result = self.engine.generate_multi_voice_audio(
                    self.dialogue_segments,
                    self.output_filename,
                    self.voice_mappings,
                    lang_code=self.lang_code,
                    speed=self.speed,
                    progress_callback=self._progress_cb,
                    return_segments=self.return_segments,
                    transition=self.transition,
                    batch_mode=self.batch_mode,
                    debug=self.debug,
                )

                # Backward-compatible handling: Path or dict
                if isinstance(result, (str, Path)):
                    combined_path = Path(result)
                    self.finished.emit(combined_path)
                elif isinstance(result, dict):
                    combined_path_raw: Any = result.get("audio_path")
                    combined_path = Path(combined_path_raw) if combined_path_raw else Path(self.output_filename)
                    segment_paths_raw: List[str] = result.get("segment_audio_paths", []) or []
                    segment_paths = [Path(p) for p in segment_paths_raw]
                    segment_timing: List[dict] = result.get("segment_timing", []) or []
                    resolved_voices: Dict[str, str] = result.get("resolved_voices", {}) or {}

                    # Emit rich multi-audio signal
                    self.multi_audio_ready.emit(combined_path, segment_paths, segment_timing, resolved_voices)
                    # Also emit finished for existing listeners that only care about the combined file
                    self.finished.emit(combined_path)
                else:
                    raise RuntimeError(f"Unexpected multi-voice result type: {type(result)!r}")
            else:
                path = self.engine.generate_audio(
                    self.text,
                    self.output_filename,
                    voice=self.voice,
                    lang_code=self.lang_code,
                    speed=self.speed,
                    progress_callback=self._progress_cb,
                )
                self.finished.emit(Path(path))
        except Exception as exc:
            tb = traceback.format_exc()
            self.error.emit(f"{exc}\n\n{tb}")


class TTSBatchThread(QThread):
    progress = Signal(str)
    batch_finished = Signal(list)   # list of output paths (str)
    error = Signal(str)

    def __init__(self, engine, chapters, filenames, voice, lang_code, speed):
        super().__init__()
        self.engine = engine
        self.chapters = chapters
        self.filenames = filenames
        self.voice = voice
        self.lang_code = lang_code
        self.speed = speed

    def _progress(self, msg: str) -> None:
        self.progress.emit(msg)

    def run(self) -> None:
        try:
            outputs: List[str] = []
            total = len(self.chapters)

            for i, (text, filename) in enumerate(zip(self.chapters, self.filenames)):
                self._progress(f"Generating chapter {i+1}/{total}...")
                path = self.engine.generate_audio(
                    text=text,
                    output_filename=filename,
                    voice=self.voice,
                    lang_code=self.lang_code,
                    speed=self.speed,
                    progress_callback=self._progress,
                )
                outputs.append(str(path))

            self.batch_finished.emit(outputs)
        except Exception as exc:
            tb = traceback.format_exc()
            self.error.emit(f"{exc}\n\n{tb}")


class TTSService(QObject):
    progress_changed = Signal(str)
    audio_ready = Signal(Path)                      # single or combined audio
    multi_audio_ready = Signal(Path, list, list, dict)  # combined_path, segment_paths, segment_timing, resolved_voices
    batch_finished = Signal(list)                  # list of output paths (str)
    error_occurred = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.engine = _make_tts_backend(settings)
        self._current_thread: Optional[QThread] = None

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _connect_tts_thread(self, thread: TTSThread) -> None:
        thread.progress.connect(self.progress_changed)
        thread.finished.connect(self.audio_ready)
        thread.multi_audio_ready.connect(self.multi_audio_ready)
        thread.error.connect(self.error_occurred)
        thread.finished.connect(thread.deleteLater)
        thread.error.connect(thread.deleteLater)

    def _connect_batch_thread(self, thread: TTSBatchThread) -> None:
        thread.progress.connect(self.progress_changed)
        thread.batch_finished.connect(self.batch_finished)
        thread.error.connect(self.error_occurred)
        thread.batch_finished.connect(thread.deleteLater)
        thread.error.connect(thread.deleteLater)

    def _is_busy(self) -> bool:
        return bool(self._current_thread and self._current_thread.isRunning())

    # ------------------------------------------------------------------ #
    # Single-voice generation
    # ------------------------------------------------------------------ #

    def generate_single_voice(
        self,
        text: str,
        output_filename: str,
        *,
        voice: str = "af_heart",
        lang_code: str = "a",
        speed: float = 1.0,
    ) -> None:
        if self._is_busy():
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
        self._connect_tts_thread(thread)
        thread.start()

    # ------------------------------------------------------------------ #
    # Multi-voice generation
    # ------------------------------------------------------------------ #

    def _get_multi_voice_options(self) -> dict:
        """Read multi-voice options from settings (with safe defaults)."""
        # These attribute names are guesses; adjust to your actual settings schema.
        return_segments = getattr(self.settings, "tts_return_segments", "combined")
        transition = getattr(self.settings, "tts_transition_mode", "silence")
        batch_mode = getattr(self.settings, "tts_batch_mode", "single")
        debug = bool(getattr(self.settings, "tts_debug", False))

        if return_segments not in {"combined", "segments", "both"}:
            return_segments = "combined"
        if transition not in {"silence", "crossfade", "none"}:
            transition = "silence"
        if batch_mode not in {"single", "batch"}:
            batch_mode = "single"

        return {
            "return_segments": return_segments,
            "transition": transition,
            "batch_mode": batch_mode,
            "debug": debug,
        }

    def generate_multi_voice(
        self,
        dialogue_segments: List,
        output_filename: str,
        voice_mappings: Dict[str, str],
        *,
        lang_code: str = "a",
        speed: float = 1.0,
    ) -> None:
        if self._is_busy():
            return

        opts = self._get_multi_voice_options()

        thread = TTSThread(
            self.engine,
            output_filename=output_filename,
            dialogue_segments=dialogue_segments,
            voice_mappings=voice_mappings,
            lang_code=lang_code,
            speed=speed,
            multi_voice=True,
            return_segments=opts["return_segments"],
            transition=opts["transition"],
            batch_mode=opts["batch_mode"],
            debug=opts["debug"],
        )
        self._current_thread = thread
        self._connect_tts_thread(thread)
        thread.start()

    # ------------------------------------------------------------------ #
    # Batch generation (single-voice chapters)
    # ------------------------------------------------------------------ #

    def generate_batch(
        self,
        chapters: List[str],
        filenames: List[str],
        *,
        voice: str,
        lang_code: str = "a",
        speed: float = 1.0,
    ) -> None:
        if self._is_busy():
            return

        thread = TTSBatchThread(
            self.engine,
            chapters,
            filenames,
            voice,
            lang_code,
            speed,
        )
        self._current_thread = thread
        self._connect_batch_thread(thread)
        thread.start()
