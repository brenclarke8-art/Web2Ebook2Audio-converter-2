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

import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Prevent ONNX Runtime / OpenMP threads from saturating all CPU cores.
# OMP_WAIT_POLICY=PASSIVE replaces the default spin-wait idle strategy with
# OS sleep, keeping cores available for the network stack.
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

app = FastAPI(title="Ebook Audio Studio — TTS Service", version="1.0.0")
_kokoro = None  # lazily initialized on first request

# ---------------------------------------------------------------------------
# Server-managed output directory
# ---------------------------------------------------------------------------

def _server_output_dir() -> Path:
    """Return the resolved output directory for generated WAV files.

    The directory is created on demand.  It is determined solely by the server
    configuration — never by caller-supplied data — to prevent path traversal.
    """
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


def _get_kokoro():
    global _kokoro
    if _kokoro is not None:
        return _kokoro

    # Belt-and-suspenders: apply thread limits even if the top-level block was
    # somehow bypassed (e.g. when the server is imported rather than run as __main__).
    _cpus = os.cpu_count() or 4
    _threads = str(max(1, _cpus - 2))
    os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
    os.environ.setdefault("OMP_NUM_THREADS", _threads)
    os.environ.setdefault("MKL_NUM_THREADS", _threads)
    os.environ.setdefault("OPENBLAS_NUM_THREADS", _threads)
    os.environ.setdefault("ONNXRUNTIME_THREADPOOL_SIZE", _threads)

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

    _kokoro = Kokoro(str(model_path), str(voices_path))
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


class PreviewRequest(BaseModel):
    voice: str = "af_heart"
    speed: float = 1.0
    lang: str = "a"


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


class AudioResponse(BaseModel):
    audio_path: str


class HealthResponse(BaseModel):
    status: str
    models_ready: bool
    model_path: str
    voices_path: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _synthesise(text: str, *, voice: str, speed: float, lang: str) -> np.ndarray:
    kokoro = _get_kokoro()
    samples, _sr = kokoro.create(text, voice=voice, speed=speed, lang=lang)
    return np.array(samples, dtype=np.float32)


def _safe_filename(filename: str) -> str:
    """Return only the base name component, rejecting empty or traversal names."""
    name = Path(filename).name
    if not name or name in (".", ".."):
        raise ValueError(f"Invalid output filename: {filename!r}")
    return name


def _write_wav(samples: np.ndarray, filename: str) -> str:
    """Write *samples* to the server-managed output directory.

    *filename* must be a plain file name (no directory components).  The
    output directory is determined by :func:`_server_output_dir` and is never
    influenced by caller-supplied data.
    """
    safe_name = _safe_filename(filename)
    out_path = _server_output_dir() / safe_name
    sf.write(str(out_path), samples, 24000)
    return str(out_path)


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
    )


@app.get("/voices")
def voices() -> dict:
    try:
        # Import the voice catalog from the installed ebook_app package if
        # available; otherwise return an empty dict.
        from ebook_app.models.voice_catalog import KOKORO_VOICE_CATALOG  # type: ignore[import]

        return {"voices": KOKORO_VOICE_CATALOG}
    except ImportError:
        return {"voices": {}}


@app.post("/synthesize", response_model=AudioResponse)
def synthesize(req: SynthesizeRequest) -> AudioResponse:
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    try:
        samples = _synthesise(req.text, voice=req.voice, speed=req.speed, lang=req.lang)
        path = _write_wav(samples, req.output_filename)
        return AudioResponse(audio_path=path)
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
    # Use integer centiseconds to avoid decimal points / OS-unsafe chars in name.
    speed_tag = int(req.speed * 100)
    filename = f"preview_{req.voice}_{speed_tag}.wav"
    try:
        samples = _synthesise(
            preview_text, voice=req.voice, speed=req.speed, lang=req.lang
        )
        path = _write_wav(samples, filename)
        return AudioResponse(audio_path=path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/synthesize_multi", response_model=AudioResponse)
def synthesize_multi(req: MultiSynthesizeRequest) -> AudioResponse:
    sample_rate = 24000
    silence_samples = int(sample_rate * req.dialogue_pause)
    silence = np.zeros(silence_samples, dtype=np.float32)

    # Build normalized speaker → voice lookup
    voice_mappings = req.voice_mappings
    narrator_voice = voice_mappings.get("narrator", "af_heart")
    all_audio: list[np.ndarray] = []
    previous_speaker: str | None = None

    try:
        for segment in req.segments:
            if not segment.text or not segment.text.strip():
                continue

            speaker = segment.speaker or "narrator"
            voice = voice_mappings.get(speaker)
            if not voice:
                gender = (segment.gender or "").strip().lower()
                if gender == "male":
                    voice = req.default_male_voice or narrator_voice
                elif gender == "female":
                    voice = req.default_female_voice or narrator_voice
                else:
                    voice = narrator_voice

            if previous_speaker is not None and previous_speaker != speaker and all_audio:
                all_audio.append(silence)

            samples = _synthesise(segment.text, voice=voice, speed=req.speed, lang=req.lang)
            all_audio.append(samples)
            previous_speaker = speaker

        if not all_audio:
            raise HTTPException(status_code=422, detail="No audio segments were generated")

        combined = np.concatenate(all_audio)
        path = _write_wav(combined, req.output_filename)
        return AudioResponse(audio_path=path)
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
