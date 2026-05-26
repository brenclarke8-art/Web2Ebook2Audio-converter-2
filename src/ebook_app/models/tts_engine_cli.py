from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import soundfile as sf

from .multispeaker import build_normalized_voice_lookup, resolve_voice_mapping
from .voice_catalog import KOKORO_VOICE_CATALOG

logger = logging.getLogger(__name__)


class TTSEngine:
    """
    Backend TTS engine using Kokoro-ONNX CLI.

    - Calls external kokoro-onnx executable for audio generation
    - Single-voice and multi-voice generation
    - Progress callbacks for GUI integration
    """

    def __init__(
        self,
        output_dir: str = "output",
        cli_path: Optional[str] = None,
        default_lang_code: str = "a",
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.cli_path = cli_path
        self.default_lang_code = default_lang_code

        if self.cli_path:
            self._verify_cli_available()

    def _verify_cli_available(self) -> None:
        """Check if the kokoro-onnx CLI is available and executable."""
        if not self.cli_path:
            raise ValueError("Kokoro CLI path not configured. Please set the path in Settings.")

        cli = Path(self.cli_path)
        if not cli.exists():
            raise FileNotFoundError(f"Kokoro CLI not found at: {self.cli_path}")

        if not cli.is_file():
            raise ValueError(f"Kokoro CLI path is not a file: {self.cli_path}")

        # Try to run with --help to verify it's executable
        try:
            result = subprocess.run(
                [str(cli), "--help"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                logger.warning(f"Kokoro CLI --help returned non-zero exit code: {result.returncode}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Kokoro CLI timed out when checking availability: {self.cli_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to execute Kokoro CLI: {e}")

    # ------------------------------------------------------------------
    # CLI execution
    # ------------------------------------------------------------------

    def _call_cli(
        self,
        text: str,
        output_path: Path,
        voice: str,
        speed: float,
        progress_callback=None,
    ) -> None:
        """Call kokoro-onnx CLI to generate audio."""
        self._verify_cli_available()

        if progress_callback:
            progress_callback("Generating audio with Kokoro CLI...")

        # Write text to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            temp_text_file = Path(f.name)
            f.write(text)

        try:
            # Build CLI command
            # Typical usage: kokoro-onnx --input text.txt --output audio.wav --voice af_heart --speed 1.0
            cmd = [
                str(self.cli_path),
                "--input", str(temp_text_file),
                "--output", str(output_path),
                "--voice", voice,
                "--speed", str(speed),
            ]

            logger.info(f"Executing: {' '.join(cmd)}")

            # Execute CLI
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode != 0:
                error_msg = f"Kokoro CLI failed with exit code {result.returncode}"
                if result.stderr:
                    error_msg += f"\nStderr: {result.stderr}"
                if result.stdout:
                    error_msg += f"\nStdout: {result.stdout}"
                raise RuntimeError(error_msg)

            if not output_path.exists():
                raise RuntimeError(f"CLI completed but output file not created: {output_path}")

            logger.info(f"Audio generated successfully: {output_path}")

        except subprocess.TimeoutExpired:
            raise RuntimeError("Kokoro CLI timed out during audio generation")
        finally:
            # Clean up temp file
            if temp_text_file.exists():
                temp_text_file.unlink()

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
                # Generate audio for this segment using CLI
                temp_filename = f"temp_segment_{i}.wav"
                temp_path = self.output_dir / temp_filename

                self._call_cli(
                    text=segment.text,
                    output_path=temp_path,
                    voice=voice,
                    speed=speed,
                    progress_callback=None,  # Avoid nested progress updates
                )

                # Load the generated audio
                audio_data, sample_rate = sf.read(str(temp_path))
                if sample_rate != 24000:
                    logger.warning(f"Expected sample rate 24000, got {sample_rate}")

                all_audio_segments.append(audio_data.astype(np.float32))

                # Clean up temp file
                temp_path.unlink()

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

        output_path = self.output_dir / output_filename

        if progress_callback:
            progress_callback("Generating audio...")

        self._call_cli(
            text=text,
            output_path=output_path,
            voice=voice,
            speed=speed,
            progress_callback=progress_callback,
        )

        if progress_callback:
            progress_callback("Audio generation complete")

        return output_path

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def list_kokoro_voices() -> Dict[str, Dict[str, str]]:
        return KOKORO_VOICE_CATALOG
