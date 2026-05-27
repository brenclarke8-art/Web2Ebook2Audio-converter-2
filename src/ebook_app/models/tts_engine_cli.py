from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import soundfile as sf

from .multispeaker_tts import build_normalized_voice_lookup, resolve_voice_mapping
from .voice_catalog import KOKORO_VOICE_CATALOG, get_lang_for_voice

logger = logging.getLogger(__name__)

# Default directory where model files are stored / downloaded to.
DEFAULT_MODELS_DIR = Path.home() / ".ebook_audio_studio" / "models"

# Hugging Face repo and filenames for Kokoro 1.0
_HF_REPO = "hexgrad/Kokoro-82M-ONNX"
_MODEL_FILENAME = "kokoro-v1.0.onnx"
_VOICES_FILENAME = "voices-v1.0.bin"


def _resolve_model_paths(
    model_path: Optional[str],
    voices_path: Optional[str],
) -> tuple[Path, Path]:
    """Return (model_path, voices_path), falling back to the default models dir."""
    default_model = DEFAULT_MODELS_DIR / _MODEL_FILENAME
    default_voices = DEFAULT_MODELS_DIR / _VOICES_FILENAME
    resolved_model = Path(model_path) if model_path else default_model
    resolved_voices = Path(voices_path) if voices_path else default_voices
    return resolved_model, resolved_voices


def download_kokoro_models(
    dest_dir: Optional[str | Path] = None,
    progress_callback=None,
) -> tuple[Path, Path]:
    """Download Kokoro 1.0 ONNX model files from Hugging Face Hub.

    Returns ``(model_path, voices_path)`` of the downloaded files.
    Raises :class:`ImportError` if *huggingface_hub* is not installed.
    """
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise ImportError(
            "huggingface_hub is required for automatic model download. "
            "Run: pip install huggingface_hub"
        ) from exc

    dest = Path(dest_dir) if dest_dir else DEFAULT_MODELS_DIR
    dest.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(f"Downloading {_MODEL_FILENAME} from Hugging Face…")
    model_path = hf_hub_download(
        repo_id=_HF_REPO,
        filename=_MODEL_FILENAME,
        local_dir=str(dest),
    )

    if progress_callback:
        progress_callback(f"Downloading {_VOICES_FILENAME} from Hugging Face…")
    voices_path = hf_hub_download(
        repo_id=_HF_REPO,
        filename=_VOICES_FILENAME,
        local_dir=str(dest),
    )

    if progress_callback:
        progress_callback("Model download complete.")

    return Path(model_path), Path(voices_path)


class TTSEngine:
    """Backend TTS engine using the kokoro-onnx Python API.

    Generates audio directly via ``kokoro_onnx.Kokoro`` without spawning any
    external process.  Model files are loaded lazily on first use.

    Model files are looked up in this order:

    1. Explicit *model_path* / *voices_path* constructor arguments.
    2. ``~/.ebook_audio_studio/models/`` (default download location).

    If the files are absent, call :meth:`download_models` (or use the
    *Download Models* button in Settings) to fetch them from Hugging Face.
    """

    def __init__(
        self,
        output_dir: str = "output",
        model_path: Optional[str] = None,
        voices_path: Optional[str] = None,
        default_lang_code: str = "a",
        # Legacy parameter kept for compatibility — ignored when using Python API
        cli_path: Optional[str] = None,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._model_path, self._voices_path = _resolve_model_paths(model_path, voices_path)
        self.default_lang_code = default_lang_code

        self._kokoro = None  # Lazy-initialised

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    def models_available(self) -> bool:
        """Return True if both model files exist on disk."""
        return self._model_path.exists() and self._voices_path.exists()

    def download_models(self, progress_callback=None) -> None:
        """Download model files and reload the engine."""
        dest = self._model_path.parent
        model, voices = download_kokoro_models(dest, progress_callback=progress_callback)
        self._model_path = model
        self._voices_path = voices
        self._kokoro = None  # Force reload

    def _get_kokoro(self):
        """Lazily initialise and return the ``Kokoro`` instance."""
        if self._kokoro is not None:
            return self._kokoro

        try:
            from kokoro_onnx import Kokoro  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "kokoro-onnx is not installed. Run: pip install kokoro-onnx"
            ) from exc

        if not self._model_path.exists():
            raise FileNotFoundError(
                f"Kokoro model file not found: {self._model_path}\n"
                "Use Settings → Download Models to fetch the model files."
            )
        if not self._voices_path.exists():
            raise FileNotFoundError(
                f"Kokoro voices file not found: {self._voices_path}\n"
                "Use Settings → Download Models to fetch the model files."
            )

        logger.info("Loading Kokoro model from %s", self._model_path)
        self._kokoro = Kokoro(str(self._model_path), str(self._voices_path))
        return self._kokoro

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_audio(
        self,
        text: str,
        output_filename: str,
        *,
        voice: str = "af_heart",
        lang_code: str = "a",
        speed: float = 1.0,
        progress_callback=None,
    ) -> Path:
        return self._generate_kokoro(
            text=text,
            output_filename=output_filename,
            voice=voice,
            speed=speed,
            progress_callback=progress_callback,
        )

    def generate_preview(
        self,
        voice: str = "af_heart",
        lang_code: str = "a",
        speed: float = 1.0,
    ) -> Path:
        preview_text = (
            "This is a preview of the selected voice at the current speed setting. "
            "Listen carefully to determine if this suits your needs."
        )
        filename = f"preview_{voice}_{speed}.wav"
        return self._generate_kokoro(
            text=preview_text,
            output_filename=filename,
            voice=voice,
            speed=speed,
        )

    def generate_multi_voice_audio(
        self,
        dialogue_segments: List,
        output_filename: str,
        voice_mappings: Dict[str, str],
        *,
        dialogue_pause: float = 0.3,
        lang_code: str = "a",
        speed: float = 1.0,
        progress_callback=None,
    ) -> Path:
        """Synthesise multi-speaker audio by concatenating per-segment audio."""
        all_audio_segments: List[np.ndarray] = []
        sample_rate = 24000
        silence_samples = int(sample_rate * dialogue_pause)
        silence = np.zeros(silence_samples, dtype=np.float32)

        previous_speaker = None
        warned_non_exact: set = set()
        normalized_lookup = build_normalized_voice_lookup(voice_mappings)

        for i, segment in enumerate(dialogue_segments):
            if not segment.text or not segment.text.strip():
                continue

            if progress_callback and i % 10 == 0:
                progress_callback(f"Processing segment {i + 1}/{len(dialogue_segments)}…")

            speaker = segment.speaker or "narrator"
            resolution = resolve_voice_mapping(
                speaker,
                voice_mappings,
                narrator_voice=voice_mappings.get("narrator", "af_heart"),
                normalized_lookup=normalized_lookup,
            )
            voice = resolution.voice

            if (
                resolution.resolution != "exact"
                and resolution.requested_speaker not in warned_non_exact
            ):
                warned_non_exact.add(resolution.requested_speaker)

            if (
                previous_speaker is not None
                and previous_speaker != speaker
                and all_audio_segments
            ):
                all_audio_segments.append(silence)

            try:
                samples = self._synthesise(segment.text, voice=voice, speed=speed)
                all_audio_segments.append(samples)
            except Exception as exc:
                logger.error("Error generating audio for segment %d: %s", i + 1, exc)

            previous_speaker = speaker

        if not all_audio_segments:
            raise ValueError("No audio segments were generated")

        if progress_callback:
            progress_callback("Combining audio segments…")

        combined_audio = np.concatenate(all_audio_segments)
        output_path = self.output_dir / output_filename

        if progress_callback:
            progress_callback("Saving audio file…")
        sf.write(str(output_path), combined_audio, sample_rate)

        if progress_callback:
            progress_callback("Audio generation complete")

        return output_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _synthesise(self, text: str, *, voice: str, speed: float) -> np.ndarray:
        """Call kokoro_onnx to produce a float32 audio array."""
        kokoro = self._get_kokoro()
        lang = get_lang_for_voice(voice)
        samples, _sr = kokoro.create(text, voice=voice, speed=speed, lang=lang)
        return np.array(samples, dtype=np.float32)

    def _generate_kokoro(
        self,
        text: str,
        output_filename: str,
        *,
        voice: str,
        speed: float,
        progress_callback=None,
    ) -> Path:
        if not text or not text.strip():
            raise ValueError("Cannot generate audio: text is empty")

        if progress_callback:
            progress_callback("Generating audio…")

        samples = self._synthesise(text, voice=voice, speed=speed)
        output_path = self.output_dir / output_filename
        sf.write(str(output_path), samples, 24000)

        if progress_callback:
            progress_callback("Audio generation complete")

        return output_path

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def list_kokoro_voices() -> Dict[str, Dict[str, str]]:
        return KOKORO_VOICE_CATALOG

