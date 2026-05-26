from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np
import soundfile as sf
import torch

from .multispeaker import build_normalized_voice_lookup, resolve_voice_mapping
from .voice_catalog import KOKORO_VOICE_CATALOG

logger = logging.getLogger(__name__)

try:
    from kokoro_tts.kokoro import KPipeline
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False


class TTSEngine:
    """
    Backend TTS engine using bundled Kokoro TTS.

    - Device auto-selection (CUDA / MPS / CPU)
    - Optional voice preloading
    - Single-voice and multi-voice generation
    - Progress callbacks for GUI integration
    """

    def __init__(
        self,
        output_dir: str = "output",
        device: str = "auto",
        preload_voices: Optional[List[str]] = None,
        default_lang_code: str = "a",
    ):
        if not KOKORO_AVAILABLE:
            raise ImportError(
                "Kokoro TTS not available. Ensure 'kokoro_tts' is bundled with the project."
            )

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.device_config = device
        self.default_lang_code = default_lang_code
        self.preload_voices = preload_voices or []

        self.device = self._select_device(device)
        logger.info(f"TTSEngine using device: {self.device}")

        self.pipeline: Optional[KPipeline] = None
        self.preloaded_voices: Dict[str, object] = {}
        self._voice_load_lock = threading.Lock()

        if self.preload_voices:
            self._preload_voices_parallel()

    # ------------------------------------------------------------------
    # Device selection
    # ------------------------------------------------------------------

    def _select_device(self, device: str) -> str:
        if device == "auto":
            if torch.cuda.is_available():
                return "cuda"
            if torch.backends.mps.is_available():
                import os

                if os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1":
                    return "mps"
                return "cpu"
            return "cpu"

        if device == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA requested but not available.")
            return "cuda"

        if device == "mps":
            if not torch.backends.mps.is_available():
                raise RuntimeError("MPS requested but not available.")
            return "mps"

        if device == "cpu":
            return "cpu"

        return self._select_device("auto")

    # ------------------------------------------------------------------
    # Voice preloading
    # ------------------------------------------------------------------

    def _ensure_pipeline(self, lang_code: str, progress_callback=None) -> None:
        if self.pipeline is not None:
            return
        if progress_callback:
            progress_callback("Loading TTS model...")
        logger.info(f"Loading Kokoro TTS model (lang={lang_code}, device={self.device})")
        self.pipeline = KPipeline(lang_code=lang_code, device=self.device)

    def _preload_voices_parallel(self) -> None:
        if not self.preload_voices:
            return

        self._ensure_pipeline(self.default_lang_code)

        def load_voice(name: str) -> None:
            try:
                voice_data = self.pipeline.load_voice(name)
                with self._voice_load_lock:
                    self.preloaded_voices[name] = voice_data
            except Exception as exc:
                logger.error(f"Failed to preload voice '{name}': {exc}")

        with ThreadPoolExecutor(max_workers=min(4, len(self.preload_voices))) as ex:
            ex.map(load_voice, self.preload_voices)

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
            lang_code=lang_code,
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
            lang_code=lang_code,
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
        """
        dialogue_segments: list of objects with .text, .speaker, .is_dialogue
        """
        self._ensure_pipeline(lang_code, progress_callback)

        all_audio_segments: List[np.ndarray] = []
        silence_samples = int(24000 * dialogue_pause)
        silence = np.zeros(silence_samples, dtype=np.float32)

        previous_speaker = None
        warned_non_exact = set()
        normalized_lookup = build_normalized_voice_lookup(voice_mappings)

        for i, segment in enumerate(dialogue_segments):
            if not segment.text or not segment.text.strip():
                continue

            if progress_callback and i % 10 == 0:
                progress_callback(f"Processing segment {i+1}/{len(dialogue_segments)}...")

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
                generator = self.pipeline(
                    segment.text,
                    voice=voice,
                    speed=speed,
                    split_pattern=r"\n+",
                )
                seg_audio: List[np.ndarray] = []
                for _, _, audio in generator:
                    seg_audio.append(audio)

                if seg_audio:
                    combined = np.concatenate(seg_audio)
                    all_audio_segments.append(combined)
                else:
                    logger.warning(f"Segment {i+1} generated no audio")

            except Exception as exc:
                logger.error(f"Error generating audio for segment {i+1}: {exc}")

            previous_speaker = speaker

        if not all_audio_segments:
            raise ValueError("No audio segments were generated")

        if progress_callback:
            progress_callback("Combining audio segments...")

        combined_audio = np.concatenate(all_audio_segments)
        output_path = self.output_dir / output_filename

        if progress_callback:
            progress_callback("Saving audio file...")
        sf.write(str(output_path), combined_audio, 24000)

        if progress_callback:
            progress_callback("Audio generation complete")

        return output_path

    # ------------------------------------------------------------------
    # Internal Kokoro generation
    # ------------------------------------------------------------------

    def _generate_kokoro(
        self,
        text: str,
        output_filename: str,
        *,
        voice: str,
        lang_code: str,
        speed: float,
        progress_callback=None,
    ) -> Path:
        if not text or not text.strip():
            raise ValueError("Cannot generate audio: text is empty")

        self._ensure_pipeline(lang_code, progress_callback)

        output_path = self.output_dir / output_filename

        if progress_callback:
            progress_callback("Generating audio...")

        generator = self.pipeline(
            text,
            voice=voice,
            speed=speed,
            split_pattern=r"\n+",
        )

        segments: List[np.ndarray] = []
        for i, (_, _, audio) in enumerate(generator):
            segments.append(audio)
            if progress_callback:
                progress_callback(f"Processing segment {i+1}...")

        if not segments:
            raise ValueError("No audio segments were generated")

        combined = np.concatenate(segments)

        if progress_callback:
            progress_callback("Saving audio file...")
        sf.write(str(output_path), combined, 24000)

        if progress_callback:
            progress_callback("Audio generation complete")

        return output_path

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def list_kokoro_voices() -> Dict[str, Dict[str, str]]:
        return KOKORO_VOICE_CATALOG
