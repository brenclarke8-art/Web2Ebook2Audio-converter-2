# ebook_app/tts/silence_trim.py
"""Silence trimming utilities for generated audio files."""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def trim_silence(
    audio_path: str | Path,
    output_path: Optional[str | Path] = None,
    threshold_db: float = -50.0,
    padding_ms: int = 100,
) -> Path:
    """
    Trim leading and trailing silence from an audio file.

    Args:
        audio_path: Input audio file path.
        output_path: Output path. If None, overwrites *audio_path*.
        threshold_db: Silence threshold in dBFS.
        padding_ms: Milliseconds of silence to keep at edges.

    Returns:
        Path to the trimmed audio file.
    """
    try:
        import soundfile as sf
    except ImportError as exc:
        raise ImportError("soundfile is required for silence trimming") from exc

    audio_path = Path(audio_path)
    output_path = Path(output_path) if output_path else audio_path

    data, samplerate = sf.read(str(audio_path))
    if data.ndim > 1:
        mono = np.mean(data, axis=1)
    else:
        mono = data

    threshold_linear = 10 ** (threshold_db / 20.0)  # dBFS → linear amplitude: amplitude = 10^(dB/20)
    padding_samples = int(samplerate * padding_ms / 1000)

    # Find first and last sample above threshold
    above = np.where(np.abs(mono) > threshold_linear)[0]
    if len(above) == 0:
        logger.debug("Audio is entirely silent, skipping trim: %s", audio_path)
        return output_path

    start = max(0, above[0] - padding_samples)
    end = min(len(data), above[-1] + padding_samples + 1)

    trimmed = data[start:end]
    sf.write(str(output_path), trimmed, samplerate)
    logger.debug("Trimmed silence: %s -> %s [%d -> %d samples]", audio_path.name, output_path.name, len(data), len(trimmed))
    return output_path
