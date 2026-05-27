"""src/ebook_app/services/tts_client.py — HTTP client adapter for the TTS service.

Provides a :class:`TTSClient` whose public API mirrors :class:`TTSEngine` so
the pipeline and UI can swap between local (direct) and remote (HTTP) backends
without any call-site changes.

Output directory handling
-------------------------
The TTS service writes every generated file to its own server-managed output
directory (configured by ``TTS_OUTPUT_DIR`` on the server side).  The client
receives the absolute path of the written file and **moves** it into the
caller-supplied ``output_dir`` so the pipeline's project layout is preserved
(``pipeline_work/audio/``).  Because client and server run on the same machine,
``shutil.move`` is always safe and atomic on most platforms.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests

from ebook_app.models.dialogue_parser import Segment

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://127.0.0.1:5005"
_TIMEOUT_HEALTH = 3       # seconds for health / quick checks
_TIMEOUT_SYNTH  = 300     # seconds for synthesis (may be long for large chapters)


class TTSServiceUnavailableError(RuntimeError):
    """Raised when the remote TTS service cannot be reached or returns an error."""


class TTSClient:
    """Thin HTTP client that calls the TTS micro-service.

    API is intentionally identical to :class:`~ebook_app.models.tts_engine_cli.TTSEngine`
    so that callers can switch between local and remote TTS without code changes.
    """

    def __init__(
        self,
        output_dir: str = "output",
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Status / availability
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if the TTS service is reachable and healthy."""
        try:
            resp = self._session.get(
                f"{self._base_url}/health", timeout=_TIMEOUT_HEALTH
            )
            resp.raise_for_status()
            return resp.json().get("status") == "ok"
        except Exception:
            return False

    def models_available(self) -> bool:
        """Return True if the remote service reports its models are ready."""
        try:
            resp = self._session.get(
                f"{self._base_url}/health", timeout=_TIMEOUT_HEALTH
            )
            resp.raise_for_status()
            return resp.json().get("models_ready", False)
        except Exception:
            return False

    def health(self) -> dict:
        """Return the raw health-check JSON or an error dict."""
        try:
            resp = self._session.get(
                f"{self._base_url}/health", timeout=_TIMEOUT_HEALTH
            )
            resp.raise_for_status()
            return resp.json()
        except requests.ConnectionError:
            return {"status": "unreachable", "models_ready": False}
        except Exception as exc:
            return {"status": "error", "models_ready": False, "detail": str(exc)}

    # ------------------------------------------------------------------
    # Public TTS API (mirrors TTSEngine)
    # ------------------------------------------------------------------

    def generate_audio(
        self,
        text: str,
        output_filename: str,
        *,
        voice: str = "af_heart",
        lang_code: str = "a",
        speed: float = 1.0,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Path:
        if progress_callback:
            progress_callback("Sending synthesis request to TTS service…")

        payload = {
            "text": text,
            "output_filename": output_filename,
            "voice": voice,
            "speed": speed,
            "lang": lang_code,
        }

        try:
            resp = self._session.post(
                f"{self._base_url}/synthesize",
                json=payload,
                timeout=_TIMEOUT_SYNTH,
            )
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            raise TTSServiceUnavailableError(
                f"TTS service unreachable at {self._base_url}. "
                "Start the service with: uvicorn tts_server:app --port 5005"
            ) from exc
        except requests.HTTPError as exc:
            detail = _extract_detail(exc.response)
            raise TTSServiceUnavailableError(
                f"TTS service returned error: {detail}"
            ) from exc

        if progress_callback:
            progress_callback("Audio generation complete")

        server_path = Path(resp.json()["audio_path"])
        dest = self.output_dir / output_filename
        if server_path != dest:
            shutil.move(str(server_path), str(dest))
        return dest

    def generate_preview(
        self,
        voice: str = "af_heart",
        lang_code: str = "a",
        speed: float = 1.0,
    ) -> Path:
        payload = {
            "voice": voice,
            "speed": speed,
            "lang": lang_code,
        }

        try:
            resp = self._session.post(
                f"{self._base_url}/preview",
                json=payload,
                timeout=_TIMEOUT_SYNTH,
            )
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            raise TTSServiceUnavailableError(
                f"TTS service unreachable at {self._base_url}"
            ) from exc
        except requests.HTTPError as exc:
            detail = _extract_detail(exc.response)
            raise TTSServiceUnavailableError(
                f"TTS service returned error: {detail}"
            ) from exc

        server_path = Path(resp.json()["audio_path"])
        dest = self.output_dir / server_path.name
        if server_path != dest:
            shutil.move(str(server_path), str(dest))
        return dest

    def generate_multi_voice_audio(
        self,
        dialogue_segments: List[Segment],
        output_filename: str,
        voice_mappings: Dict[str, str],
        *,
        default_male_voice: str = "am_adam",
        default_female_voice: str = "af_heart",
        dialogue_pause: float = 0.3,
        lang_code: str = "a",
        speed: float = 1.0,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Path:
        if progress_callback:
            progress_callback("Sending multi-voice synthesis request…")

        segments_payload = [
            {
                "text": s.text,
                "speaker": s.speaker,
                "kind": s.kind,
                "gender": getattr(s, "gender", "unknown"),
                "paragraph_id": s.paragraph_id,
            }
            for s in dialogue_segments
        ]

        payload = {
            "segments": segments_payload,
            "output_filename": output_filename,
            "voice_mappings": voice_mappings,
            "default_male_voice": default_male_voice,
            "default_female_voice": default_female_voice,
            "speed": speed,
            "lang": lang_code,
            "dialogue_pause": dialogue_pause,
        }

        try:
            resp = self._session.post(
                f"{self._base_url}/synthesize_multi",
                json=payload,
                timeout=_TIMEOUT_SYNTH,
            )
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            raise TTSServiceUnavailableError(
                f"TTS service unreachable at {self._base_url}"
            ) from exc
        except requests.HTTPError as exc:
            detail = _extract_detail(exc.response)
            raise TTSServiceUnavailableError(
                f"TTS service returned error: {detail}"
            ) from exc

        if progress_callback:
            progress_callback("Multi-voice audio generation complete")

        server_path = Path(resp.json()["audio_path"])
        dest = self.output_dir / output_filename
        if server_path != dest:
            shutil.move(str(server_path), str(dest))
        return dest

    # ------------------------------------------------------------------
    # Utility (matches TTSEngine.list_kokoro_voices)
    # ------------------------------------------------------------------

    @staticmethod
    def list_kokoro_voices() -> dict:
        """Return the voice catalog — imported from the local voice_catalog module."""
        try:
            from ebook_app.models.voice_catalog import KOKORO_VOICE_CATALOG  # type: ignore[import]

            return KOKORO_VOICE_CATALOG
        except ImportError:
            return {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_detail(response: requests.Response) -> str:
    """Extract a human-readable error detail from an error response."""
    try:
        return response.json().get("detail", response.text)
    except Exception:
        return response.text
