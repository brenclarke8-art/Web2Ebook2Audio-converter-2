"""src/ebook_app/services/tts_client.py — Thin HTTP client for the TTS backend service."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_DEFAULT_URL = "http://127.0.0.1:5005"


class TTSClient:
    """Lightweight wrapper around the TTS service REST API."""

    def __init__(self, base_url: str = _DEFAULT_URL, timeout: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict:
        """GET /health — returns a dict with keys: status, models_ready, model_path, etc."""
        import requests

        url = f"{self.base_url}/health"
        try:
            resp = requests.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.debug("TTS health check failed: %s", exc)
            return {"status": "unreachable", "detail": str(exc)}

    def preview(self, voice: str = "af_heart", speed: float = 1.0, lang: str = "a") -> dict:
        """POST /preview — synthesise a short preview phrase and return audio_path.

        Args:
            voice: Voice name recognised by the server (e.g. "af_heart").
            speed: Playback speed multiplier (0.5–2.0).
            lang: Language/phonemiser code; "a" selects American English.
        """
        import requests

        # Use a longer timeout for synthesis which may take several seconds on first run.
        synthesis_timeout = max(self.timeout, 30)
        url = f"{self.base_url}/preview"
        payload = {"voice": voice, "speed": speed, "lang": lang}
        try:
            resp = requests.post(url, json=payload, timeout=synthesis_timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.debug("TTS preview failed: %s", exc)
            return {"error": str(exc)}
