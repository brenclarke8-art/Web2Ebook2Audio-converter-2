"""
src/ebook_app/services/tts_client.py — HTTP client adapter for the TTS service.

Upgraded to support:
- return_segments
- transition modes
- batch_mode
- segment-level preview
- per-segment re-synthesis
- timing metadata validation
- resolved voice merging
- configurable move/copy behavior
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import requests

from ebook_app.models.dialogue_parser import Segment

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://127.0.0.1:5005"
_TIMEOUT_HEALTH = 3
_TIMEOUT_SYNTH = 300


class TTSServiceUnavailableError(RuntimeError):
    pass


class TTSClient:
    """
    Remote TTS client that mirrors the TTSEngine API.
    """

    def __init__(
        self,
        output_dir: str = "output",
        base_url: str = _DEFAULT_BASE_URL,
        *,
        move_mode: str = "move",  # "move" | "copy"
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()

        if move_mode not in {"move", "copy"}:
            move_mode = "move"
        self._move_mode = move_mode

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _move_or_copy(self, src: Path, dest: Path) -> None:
        """Move or copy based on configuration."""
        if self._move_mode == "copy":
            shutil.copy2(str(src), str(dest))
            src.unlink(missing_ok=True)
        else:
            shutil.move(str(src), str(dest))

    def _validate_timing(self, timing: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ensure timing metadata is sorted and non-overlapping."""
        if not timing:
            return timing

        # Sort by start_ms
        timing = sorted(timing, key=lambda x: x.get("start_ms", 0))

        fixed = []
        last_end = 0.0

        for item in timing:
            start = max(0.0, float(item.get("start_ms", 0)))
            end = max(start, float(item.get("end_ms", start)))

            # Fix overlaps
            if start < last_end:
                start = last_end
                end = max(end, start)

            fixed.append({
                "start_ms": start,
                "end_ms": end,
                "speaker": item.get("speaker", ""),
                "paragraph_id": item.get("paragraph_id", ""),
            })

            last_end = end

        return fixed

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        try:
            resp = self._session.get(f"{self._base_url}/health", timeout=_TIMEOUT_HEALTH)
            resp.raise_for_status()
            return resp.json().get("status") == "ok"
        except Exception:
            return False

    def models_available(self) -> bool:
        try:
            resp = self._session.get(f"{self._base_url}/health", timeout=_TIMEOUT_HEALTH)
            resp.raise_for_status()
            return resp.json().get("models_ready", False)
        except Exception:
            return False

    def health(self) -> dict:
        try:
            resp = self._session.get(f"{self._base_url}/health", timeout=_TIMEOUT_HEALTH)
            resp.raise_for_status()
            return resp.json()
        except requests.ConnectionError:
            return {"status": "unreachable", "models_ready": False}
        except Exception as exc:
            return {"status": "error", "models_ready": False, "detail": str(exc)}

    # ------------------------------------------------------------------
    # Single-voice synthesis
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
            progress_callback("Sending synthesis request…")

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
        except Exception as exc:
            raise TTSServiceUnavailableError(str(exc)) from exc

        data = resp.json()
        server_path = Path(data["audio_path"])
        dest = self.output_dir / output_filename
        self._move_or_copy(server_path, dest)

        if progress_callback:
            progress_callback("Audio generation complete")

        return dest

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def generate_preview(
        self,
        voice: str = "af_heart",
        lang_code: str = "a",
        speed: float = 1.0,
    ) -> Path:
        payload = {"voice": voice, "speed": speed, "lang": lang_code}

        try:
            resp = self._session.post(
                f"{self._base_url}/preview",
                json=payload,
                timeout=_TIMEOUT_SYNTH,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise TTSServiceUnavailableError(str(exc)) from exc

        data = resp.json()
        server_path = Path(data["audio_path"])
        dest = self.output_dir / server_path.name
        self._move_or_copy(server_path, dest)
        return dest

    # ------------------------------------------------------------------
    # Multi-voice synthesis (always returns dict)
    # ------------------------------------------------------------------

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
        return_segments: str = "combined",
        transition: str = "silence",
        batch_mode: str = "single",
        debug: bool = False,
    ) -> Dict[str, Any]:
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
            "transition": transition,
            "return_segments": return_segments,
            "batch_mode": batch_mode,
            "debug": debug,
        }

        try:
            resp = self._session.post(
                f"{self._base_url}/synthesize_multi",
                json=payload,
                timeout=_TIMEOUT_SYNTH,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise TTSServiceUnavailableError(str(exc)) from exc

        data = resp.json()

        # Combined audio
        combined_dest = None
        if data.get("audio_path"):
            server_combined = Path(data["audio_path"])
            combined_dest = self.output_dir / output_filename
            self._move_or_copy(server_combined, combined_dest)

        # Segment audio
        segment_dest_paths: List[str] = []
        for seg_server_path in data.get("segment_audio_paths", []) or []:
            sp = Path(seg_server_path)
            dest = self.output_dir / sp.name
            self._move_or_copy(sp, dest)
            segment_dest_paths.append(str(dest))

        # Timing validation
        timing = self._validate_timing(data.get("segment_timing", []) or [])

        # Merge resolved voices
        resolved = data.get("resolved_voices", {}) or {}
        merged_voices = {**voice_mappings, **resolved}

        result = {
            "audio_path": str(combined_dest) if combined_dest else None,
            "segment_audio_paths": segment_dest_paths,
            "segment_timing": timing,
            "resolved_voices": merged_voices,
        }

        if progress_callback:
            progress_callback("Multi-voice synthesis complete")

        return result

    # ------------------------------------------------------------------
    # Segment-level preview
    # ------------------------------------------------------------------

    def generate_segment_preview(
        self,
        text: str,
        *,
        voice: str = "af_heart",
        lang_code: str = "a",
        speed: float = 1.0,
    ) -> Path:
        payload = {"text": text, "voice": voice, "speed": speed, "lang": lang_code}

        try:
            resp = self._session.post(
                f"{self._base_url}/synthesize_segment",
                json=payload,
                timeout=_TIMEOUT_SYNTH,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise TTSServiceUnavailableError(str(exc)) from exc

        data = resp.json()
        server_path = Path(data["audio_path"])
        dest = self.output_dir / server_path.name
        self._move_or_copy(server_path, dest)
        return dest

    # ------------------------------------------------------------------
    # Per-segment re-synthesis
    # ------------------------------------------------------------------

    def regenerate_single_segment(
        self,
        segment: Segment,
        *,
        voice: str,
        lang_code: str = "a",
        speed: float = 1.0,
    ) -> Dict[str, Any]:
        """Re-synthesize a single segment and return metadata."""
        payload = {
            "text": segment.text,
            "voice": voice,
            "speed": speed,
            "lang": lang_code,
        }

        try:
            resp = self._session.post(
                f"{self._base_url}/synthesize_segment",
                json=payload,
                timeout=_TIMEOUT_SYNTH,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise TTSServiceUnavailableError(str(exc)) from exc

        data = resp.json()
        server_path = Path(data["audio_path"])
        dest = self.output_dir / server_path.name
        self._move_or_copy(server_path, dest)

        return {
            "audio_path": str(dest),
            "duration_ms": data.get("duration_ms"),
            "resolved_voice": data.get("resolved_voice"),
        }

    # ------------------------------------------------------------------
    # Voice catalog
    # ------------------------------------------------------------------

    @staticmethod
    def list_kokoro_voices() -> dict:
        try:
            from ebook_app.models.voice_catalog import KOKORO_VOICE_CATALOG
            return KOKORO_VOICE_CATALOG
        except ImportError:
            return {}


def _extract_detail(response: requests.Response) -> str:
    try:
        return response.json().get("detail", response.text)
    except Exception:
        return response.text
