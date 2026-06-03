from __future__ import annotations

import logging
import time
import requests
import soundfile as sf
import numpy as np
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


class TTSEngine:
    """
    Contract-compliant TTS engine that communicates with the local FastAPI
    Kokoro TTS server.

    Implements TTSEngineContract:
      - generate_audio()
      - get_last_audio_duration()
      - concatenate_audio_files()
    """

    def __init__(
        self,
        *,
        server_url: str = "http://127.0.0.1:5005",
        output_dir: str | Path,
        timeout: int = 30,
        retry_attempts: int = 3,
        retry_backoff_sec: float = 0.75,
    ):
        self.server_url = server_url.rstrip("/")
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.retry_attempts = max(1, int(retry_attempts))
        self.retry_backoff_sec = max(0.0, float(retry_backoff_sec))

        self._last_duration_sec: float = 0.0

    # ------------------------------------------------------------------
    # Contract: generate_audio
    # ------------------------------------------------------------------

    def generate_audio(
        self,
        *,
        text: str,
        output_filename: str,
        voice: str,
        speed: float,
    ) -> Path:
        """
        Generate a single WAV file using the TTS server.

        The server writes the file to its own output directory and returns
        the absolute path. We then copy it into our pipeline output_dir.
        """

        if not text.strip():
            raise ValueError("TTS text must not be empty")

        payload = {
            "text": text,
            "output_filename": output_filename,
            "voice": voice,
            "speed": float(speed),
        }

        url = f"{self.server_url}/synthesize"
        resp = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                resp = requests.post(url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                break
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                detail = self._error_detail_from_response(exc.response)
                if status == 503 and attempt < self.retry_attempts:
                    if self._is_non_retryable_503(detail):
                        logger.error(
                            "TTS server returned non-retryable 503: %s",
                            detail or "service unavailable",
                        )
                        raise
                    logger.warning(
                        "TTS server returned 503%s; retrying request (%d/%d).",
                        f" ({detail})" if detail else "",
                        attempt,
                        self.retry_attempts,
                    )
                    time.sleep(max(1.0, self.retry_backoff_sec * attempt))
                    continue
                logger.error("TTS server request failed: %s%s", exc, f" | detail={detail}" if detail else "")
                raise
            except requests.RequestException as exc:
                if attempt < self.retry_attempts:
                    logger.warning(
                        "TTS server request failed; retrying (%d/%d): %s",
                        attempt,
                        self.retry_attempts,
                        exc,
                    )
                    time.sleep(self.retry_backoff_sec * attempt)
                    continue
                logger.error("TTS server request failed: %s", exc)
                raise

        data = resp.json()
        server_path = Path(data["audio_path"])
        duration_ms = data.get("duration_ms", 0)

        # Convert ms → seconds
        self._last_duration_sec = float(duration_ms) / 1000.0

        # Copy file into our pipeline output directory
        local_path = self.output_dir / output_filename
        try:
            local_path.write_bytes(server_path.read_bytes())
        except Exception as exc:
            logger.error("Failed to copy TTS output from server: %s", exc)
            raise

        return local_path

    @staticmethod
    def _error_detail_from_response(response: requests.Response | None) -> str:
        if response is None:
            return ""
        try:
            payload = response.json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if detail:
                return str(detail).strip()
        body = (response.text or "").strip()
        return body[:240]

    @staticmethod
    def _is_non_retryable_503(detail: str) -> bool:
        lowered = (detail or "").lower()
        return any(
            marker in lowered
            for marker in (
                "not installed",
                "not found",
                "no such file",
                "missing",
                "set kokoro_model_path",
                "set kokoro_voices_path",
            )
        )

    # ------------------------------------------------------------------
    # Contract: get_last_audio_duration
    # ------------------------------------------------------------------

    def get_last_audio_duration(self) -> float:
        return self._last_duration_sec

    # ------------------------------------------------------------------
    # Contract: concatenate_audio_files
    # ------------------------------------------------------------------

    def concatenate_audio_files(
        self,
        files: List[str],
        output_path: Path,
    ) -> None:
        """
        Concatenate multiple WAV files into a single WAV file.

        Uses soundfile to read/append PCM data.
        """

        if not files:
            raise ValueError("No audio files provided for concatenation")

        pcm_list = []
        sample_rate = None

        for f in files:
            try:
                data, sr = sf.read(f, dtype="float32")
            except Exception as exc:
                logger.error("Failed to read WAV file %s: %s", f, exc)
                raise

            if sample_rate is None:
                sample_rate = sr
            elif sr != sample_rate:
                raise RuntimeError(f"Sample rate mismatch: {f} has {sr}, expected {sample_rate}")

            pcm_list.append(data)

        combined = np.concatenate(pcm_list, axis=0)

        try:
            sf.write(str(output_path), combined, sample_rate)
        except Exception as exc:
            logger.error("Failed to write concatenated WAV: %s", exc)
            raise
