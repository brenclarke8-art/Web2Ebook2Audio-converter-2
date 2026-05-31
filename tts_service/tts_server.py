"""tts_service/tts_server.py — standalone FastAPI TTS backend.

Run with::

    cd tts_service
    pip install -r requirements.txt
    uvicorn tts_server:app --host 127.0.0.1 --port 5005

The server loads the Kokoro-ONNX model once at startup and exposes a small
REST API that the Python 3.10 GUI can call without importing kokoro_onnx
directly.

Output directory
----------------
The server writes every generated WAV file to a server-managed output
directory.  The directory is determined by (in order of precedence):

1. The ``TTS_OUTPUT_DIR`` environment variable.
2. The ``<repo>/output`` directory.

Clients receive the absolute path of the written file in every response and
are responsible for moving or copying it to their own desired location if
needed.  The server never accepts a caller-supplied output path, which
prevents path-traversal vulnerabilities.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Dict, List, Literal, Optional

# ---------------------------------------------------------------------------
# Prevent ONNX Runtime / OpenMP threads from saturating all CPU cores.
# ---------------------------------------------------------------------------
_cpu_count: int = os.cpu_count() or 4
_onnx_threads: str = str(max(1, _cpu_count - 2))
os.environ.setdefault("OMP_NUM_THREADS", _onnx_threads)
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
os.environ.setdefault("MKL_NUM_THREADS", _onnx_threads)
os.environ.setdefault("OPENBLAS_NUM_THREADS", _onnx_threads)
os.environ.setdefault("ONNXRUNTIME_THREADPOOL_SIZE", _onnx_threads)

import numpy as np
import soundfile as sf
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("tts_server")

# ---------------------------------------------------------------------------
# Model directory — mirrors the main app default
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_HOME_DIR = Path(
    os.environ.get("EBOOK_AUDIO_STUDIO_HOME", str(REPO_ROOT / ".ebook_audio_studio"))
).expanduser().resolve()
DEFAULT_MODELS_DIR = APP_HOME_DIR / "models"
DEFAULT_OUTPUT_DIR = (REPO_ROOT / "output").resolve()
_MODEL_FILENAME = "kokoro-v1.0.onnx"
_VOICES_FILENAME = "voices-v1.0.bin"

# ---------------------------------------------------------------------------
# App + lazy-loaded engine
# ---------------------------------------------------------------------------

app = FastAPI(title="Ebook Audio Studio — TTS Service", version="1.1.0")
_kokoro = None  # lazily initialized on first request
_kokoro_voices: Dict[str, dict] | None = None  # optional voice catalog from kokoro
_kokoro_provider: str | None = None  # "gpu" or "cpu"

SAMPLE_RATE = 24000


# ---------------------------------------------------------------------------
# Server-managed output directory
# ---------------------------------------------------------------------------

def _server_output_dir() -> Path:
    env_val = os.environ.get("TTS_OUTPUT_DIR")
    base = Path(env_val).expanduser().resolve() if env_val else DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base


def _get_model_paths() -> tuple[Path, Path]:
    model_path_env = os.environ.get("KOKORO_MODEL_PATH")
    voices_path_env = os.environ.get("KOKORO_VOICES_PATH")
    model_path = Path(model_path_env) if model_path_env else DEFAULT_MODELS_DIR / _MODEL_FILENAME
    voices_path = Path(voices_path_env) if voices_path_env else DEFAULT_MODELS_DIR / _VOICES_FILENAME
    return model_path, voices_path


def _load_kokoro_model():
    """Load Kokoro with GPU-first, CPU-fallback strategy."""
    global _kokoro, _kokoro_voices, _kokoro_provider

    try:
        from kokoro_onnx import Kokoro  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "kokoro-onnx is not installed. Run: pip install kokoro-onnx"
        ) from exc

    model_path, voices_path = _get_model_paths()

    if not model_path.exists():
        raise FileNotFoundError(
            f"Kokoro model file not found: {model_path}\n"
            "Set KOKORO_MODEL_PATH env var or download models to "
            f"{DEFAULT_MODELS_DIR}"
        )
    if not voices_path.exists():
        raise FileNotFoundError(
            f"Kokoro voices file not found: {voices_path}\n"
            "Set KOKORO_VOICES_PATH env var or download models to "
            f"{DEFAULT_MODELS_DIR}"
        )

    # GPU-first, CPU-fallback
    provider = "cpu"
    try:
        _kokoro = Kokoro(str(model_path), str(voices_path), device="cuda")  # type: ignore[call-arg]
        provider = "gpu"
    except Exception:
        _kokoro = Kokoro(str(model_path), str(voices_path))
        provider = "cpu"

    _kokoro_provider = provider
    logger.info("Kokoro model loaded using provider: %s", provider)

    # Try to expose voice catalog if available
    try:
        voices = getattr(_kokoro, "voices", None)
        if isinstance(voices, dict):
            _kokoro_voices = voices
    except Exception:
        _kokoro_voices = None


def _get_kokoro():
    global _kokoro
    if _kokoro is not None:
        return _kokoro

    # Re-apply thread limits
    _cpus = os.cpu_count() or 4
    _threads = str(max(1, _cpus - 2))
    os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
    os.environ.setdefault("OMP_NUM_THREADS", _threads)
    os.environ.setdefault("MKL_NUM_THREADS", _threads)
    os.environ.setdefault("OPENBLAS_NUM_THREADS", _threads)
    os.environ.setdefault("ONNXRUNTIME_THREADPOOL_SIZE", _threads)

    _load_kokoro_model()
    return _kokoro


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SynthesizeRequest(BaseModel):
    text: str
    output_filename: str
    voice: str = "af_heart"
    speed: float = 1.0
    lang: str = "a"
    debug: bool = False


class PreviewRequest(BaseModel):
    voice: str = "af_heart"
    speed: float = 1.0
    lang: str = "a"
    debug: bool = False


class SegmentItem(BaseModel):
    text: str
    speaker: str = "narrator"
    kind: str = "narration"
    gender: str = "unknown"
    paragraph_id: str = ""


class MultiSynthesizeRequest(BaseModel):
    segments: List[SegmentItem]
    output_filename: str
    voice_mappings: Dict[str, str] = {}
    default_male_voice: str = "am_adam"
    default_female_voice: str = "af_heart"
    speed: float = 1.0
    lang: str = "a"
    dialogue_pause: float = 0.3
    transition: Literal["silence", "crossfade", "none"] = "silence"
    return_segments: Literal["combined", "segments", "both"] = "combined"
    batch_mode: Literal["batch", "single"] = "single"
    debug: bool = False


class AudioResponse(BaseModel):
    audio_path: str
    duration_ms: Optional[int] = None
    resolved_voice: Optional[str] = None


class MultiAudioResponse(BaseModel):
    audio_path: Optional[str] = None
    duration_ms: Optional[int] = None
    segment_audio_paths: List[str] = []
    segment_timing: List[Dict[str, float]] = []  # {start_ms, end_ms, speaker, paragraph_id}
    resolved_voices: Dict[str, str] = {}  # speaker -> voice


class HealthResponse(BaseModel):
    status: str
    models_ready: bool
    model_path: str
    voices_path: str
    provider: Optional[str] = None


# --- Segment-level TTS models ----------------------------------------------

class SegmentTTSRequest(BaseModel):
    text: str
    voice: str = "af_heart"
    speed: float = 1.0
    lang: str = "a"
    debug: bool = False


class SegmentTTSResponse(BaseModel):
    audio_path: str
    duration_ms: Optional[int] = None
    resolved_voice: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_or_fallback_voice(voice: str, default_voice: str = "af_heart") -> str:
    """Hybrid voice routing: trust client, but validate against known voices if available."""
    if not voice:
        return default_voice

    if _kokoro_voices is None:
        # No catalog available, trust client
        return voice

    if voice in _kokoro_voices:
        return voice

    logger.warning("Requested voice '%s' not found in Kokoro catalog; falling back to '%s'", voice, default_voice)
    return default_voice


def _synthesise(text: str, *, voice: str, speed: float, lang: str, debug: bool = False) -> np.ndarray:
    kokoro = _get_kokoro()
    resolved_voice = _validate_or_fallback_voice(voice)
    if debug:
        logger.debug("Synthesizing text with voice=%s (requested=%s), speed=%.3f, lang=%s", resolved_voice, voice, speed, lang)
    samples, _sr = kokoro.create(text, voice=resolved_voice, speed=speed, lang=lang)
    return np.array(samples, dtype=np.float32)


def _safe_filename(filename: str) -> str:
    name = Path(filename).name
    if not name or name in (".", ".."):
        raise ValueError(f"Invalid output filename: {filename!r}")
    return name


def _write_wav(samples: np.ndarray, filename: str) -> str:
    safe_name = _safe_filename(filename)
    out_path = _server_output_dir() / safe_name
    sf.write(str(out_path), samples, SAMPLE_RATE)
    return str(out_path)


def _duration_ms(samples: np.ndarray) -> int:
    if samples.size == 0:
        return 0
    return int(round(len(samples) / SAMPLE_RATE * 1000))


def _crossfade(a: np.ndarray, b: np.ndarray, fade_ms: float = 120.0) -> np.ndarray:
    """Equal-power crossfade between two segments."""
    if a.size == 0:
        return b
    if b.size == 0:
        return a

    fade_samples = int(SAMPLE_RATE * (fade_ms / 1000.0))
    fade_samples = max(1, min(fade_samples, min(len(a), len(b))))

    a_main = a[:-fade_samples]
    a_tail = a[-fade_samples:]
    b_head = b[:fade_samples]
    b_rest = b[fade_samples:]

    t = np.linspace(0.0, 1.0, fade_samples, endpoint=False, dtype=np.float32)
    fade_out = np.sqrt(1.0 - t)
    fade_in = np.sqrt(t)

    mixed = a_tail * fade_out + b_head * fade_in
    return np.concatenate([a_main, mixed, b_rest])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    model_path, voices_path = _get_model_paths()
    models_ready = model_path.exists() and voices_path.exists()
    return HealthResponse(
        status="ok",
        models_ready=models_ready,
        model_path=str(model_path),
        voices_path=str(voices_path),
        provider=_kokoro_provider,
    )


@app.get("/voices")
def voices() -> dict:
    try:
        # Prefer Kokoro's own catalog if available
        if _kokoro_voices is not None:
            return {"voices": _kokoro_voices}
        from ebook_app.models.voice_catalog import KOKORO_VOICE_CATALOG  # type: ignore[import]
        return {"voices": KOKORO_VOICE_CATALOG}
    except ImportError:
        return {"voices": {}}


@app.post("/synthesize", response_model=AudioResponse)
def synthesize(req: SynthesizeRequest) -> AudioResponse:
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    try:
        resolved_voice = _validate_or_fallback_voice(req.voice)
        samples = _synthesise(req.text, voice=resolved_voice, speed=req.speed, lang=req.lang, debug=req.debug)
        path = _write_wav(samples, req.output_filename)
        return AudioResponse(
            audio_path=path,
            duration_ms=_duration_ms(samples),
            resolved_voice=resolved_voice,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/preview", response_model=AudioResponse)
def preview(req: PreviewRequest) -> AudioResponse:
    preview_text = (
        "This is a preview of the selected voice at the current speed setting. "
        "Listen carefully to determine if this suits your needs."
    )
    speed_tag = int(req.speed * 100)
    filename = f"preview_{req.voice}_{speed_tag}.wav"
    try:
        resolved_voice = _validate_or_fallback_voice(req.voice)
        samples = _synthesise(preview_text, voice=resolved_voice, speed=req.speed, lang=req.lang, debug=req.debug)
        path = _write_wav(samples, filename)
        return AudioResponse(
            audio_path=path,
            duration_ms=_duration_ms(samples),
            resolved_voice=resolved_voice,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# --- Segment-level TTS endpoint --------------------------------------------

@app.post("/synthesize_segment", response_model=SegmentTTSResponse)
def synthesize_segment(req: SegmentTTSRequest) -> SegmentTTSResponse:
    """
    Generate TTS audio for a single semantic segment.
    Used by the GUI for segment-level preview.
    """
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")

    speed_tag = int(req.speed * 100)
    filename = f"segment_{uuid.uuid4().hex}_{req.voice}_{speed_tag}.wav"

    try:
        resolved_voice = _validate_or_fallback_voice(req.voice)
        samples = _synthesise(req.text, voice=resolved_voice, speed=req.speed, lang=req.lang, debug=req.debug)
        path = _write_wav(samples, filename)
        return SegmentTTSResponse(
            audio_path=path,
            duration_ms=_duration_ms(samples),
            resolved_voice=resolved_voice,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/synthesize_multi", response_model=MultiAudioResponse)
def synthesize_multi(req: MultiSynthesizeRequest) -> MultiAudioResponse:
    """
    Multi-segment synthesis with:
    - hybrid voice validation
    - optional per-segment WAVs
    - optional combined WAV
    - silence / crossfade / none transitions
    - optional batch vs single synthesis mode (currently single-call per segment)
    """
    sample_rate = SAMPLE_RATE
    silence_samples = int(sample_rate * req.dialogue_pause)
    silence = np.zeros(silence_samples, dtype=np.float32)

    voice_mappings = req.voice_mappings
    narrator_voice = voice_mappings.get("narrator", req.default_female_voice or "af_heart")

    all_audio: list[np.ndarray] = []
    segment_paths: list[str] = []
    segment_timing: list[Dict[str, float]] = []
    resolved_voices: Dict[str, str] = {}

    previous_speaker: str | None = None
    current_time_ms: float = 0.0

    try:
        # For now, we honor batch_mode flag but still synthesize per segment;
        # batch synthesis would require deeper integration with Kokoro internals.
        for idx, segment in enumerate(req.segments):
            if not segment.text or not segment.text.strip():
                continue

            speaker = segment.speaker or "narrator"
            kind = (segment.kind or "narration").strip().lower()
            gender = (segment.gender or "").strip().lower()

            # Narration segments always use narrator voice
            if kind == "narration":
                requested_voice = voice_mappings.get("narrator", narrator_voice)
            else:
                requested_voice = voice_mappings.get(speaker)
                if not requested_voice:
                    if gender == "male":
                        requested_voice = req.default_male_voice or narrator_voice
                    elif gender == "female":
                        requested_voice = req.default_female_voice or narrator_voice
                    else:
                        requested_voice = narrator_voice

            resolved_voice = _validate_or_fallback_voice(requested_voice, default_voice=narrator_voice)
            resolved_voices.setdefault(speaker, resolved_voice)

            if req.debug:
                logger.debug(
                    "Segment %d: speaker=%s kind=%s gender=%s requested_voice=%s resolved_voice=%s",
                    idx,
                    speaker,
                    kind,
                    gender,
                    requested_voice,
                    resolved_voice,
                )

            # Transition handling between speakers
            if previous_speaker is not None and previous_speaker != speaker and all_audio:
                if req.transition == "silence":
                    all_audio.append(silence)
                    current_time_ms += req.dialogue_pause * 1000.0
                elif req.transition == "crossfade":
                    # crossfade will be applied when concatenating; handled below
                    pass
                # "none" means no explicit transition
            previous_speaker = speaker

            # Synthesize this segment
            samples = _synthesise(segment.text, voice=resolved_voice, speed=req.speed, lang=req.lang, debug=req.debug)

            # Optional per-segment WAV
            seg_path: Optional[str] = None
            if req.return_segments in {"segments", "both"}:
                seg_filename = f"segment_{idx}_{uuid.uuid4().hex}_{resolved_voice}.wav"
                seg_path = _write_wav(samples, seg_filename)
                segment_paths.append(seg_path)

            # Track timing
            seg_duration_ms = _duration_ms(samples)
            segment_timing.append(
                {
                    "start_ms": current_time_ms,
                    "end_ms": current_time_ms + seg_duration_ms,
                    "speaker": speaker,
                    "paragraph_id": segment.paragraph_id or "",
                }
            )
            current_time_ms += seg_duration_ms

            # Store audio for combined output
            all_audio.append(samples)

        if not all_audio:
            raise HTTPException(status_code=422, detail="No audio segments were generated")

        # Build combined audio with transitions
        if req.transition == "crossfade" and len(all_audio) > 1:
            combined = all_audio[0]
            for part in all_audio[1:]:
                combined = _crossfade(combined, part)
        else:
            combined = np.concatenate(all_audio)

        combined_path: Optional[str] = None
        if req.return_segments in {"combined", "both"}:
            combined_path = _write_wav(combined, req.output_filename)

        return MultiAudioResponse(
            audio_path=combined_path,
            duration_ms=_duration_ms(combined),
            segment_audio_paths=segment_paths,
            segment_timing=segment_timing,
            resolved_voices=resolved_voices,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ebook Audio Studio TTS Service")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5005, help="Bind port (default: 5005)")
    args = parser.parse_args()

    uvicorn.run("tts_server:app", host=args.host, port=args.port, reload=False)
