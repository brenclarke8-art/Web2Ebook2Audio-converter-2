# src/ebook_app/models/tts_engine_cli.py
"""Wrapper for the ONNX-based Kokoro TTS CLI executable."""

from __future__ import annotations

import subprocess
from pathlib import Path


class TTSEngineCLI:
    """Thin wrapper around the Kokoro ONNX CLI binary.

    Calls the CLI as a subprocess and returns the path to the generated WAV.

    Usage::

        engine = TTSEngineCLI(cli_path="/usr/local/bin/kokoro-onnx")
        wav_path = engine.synthesise(
            text="Hello, world!",
            voice="af_heart",
            output_path="/tmp/hello.wav",
            speed=1.0,
        )

    TODO: populate argument names once the real Kokoro CLI is available.
    """

    def __init__(self, cli_path: str) -> None:
        self.cli_path = cli_path

    def synthesise(
        self,
        text: str,
        voice: str,
        output_path: str,
        speed: float = 1.0,
    ) -> str:
        """Invoke the Kokoro CLI to synthesise *text* to *output_path*.

        :param text:        The text to synthesise.
        :param voice:       Voice identifier (e.g. ``af_heart``).
        :param output_path: Destination WAV file path.
        :param speed:       Playback speed multiplier.
        :returns:           Absolute path to the generated WAV file.
        :raises FileNotFoundError: If ``cli_path`` is empty or not executable.
        :raises RuntimeError:      If the CLI exits with a non-zero code.

        TODO: adjust CLI argument names to match the real Kokoro binary.
        """
        if not self.cli_path:
            raise FileNotFoundError("Kokoro CLI path is not configured.")

        cmd = [
            self.cli_path,
            "--text", text,
            "--voice", voice,
            "--output", output_path,
            "--speed", str(speed),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
        if result.returncode != 0:
            raise RuntimeError(
                f"Kokoro CLI failed (exit {result.returncode}): {result.stderr}"
            )

        return str(Path(output_path).resolve())
