from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("tts_service")

try:
    from kokoro_onnx import Kokoro
except Exception:  # pragma: no cover - import availability depends on runtime env
    Kokoro = None

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_HOME = Path(os.environ.get("EBOOK_AUDIO_STUDIO_HOME", ROOT_DIR / ".ebook_audio_studio")).resolve()
SETTINGS_PATH = APP_HOME / "settings.json"
MODELS_DIR = APP_HOME / "models"
OUTPUT_DIR = APP_HOME / "tts_service_output"

DEFAULT_MODEL_PATH = MODELS_DIR / "kokoro-v1.0.onnx"
DEFAULT_VOICES_PATH = MODELS_DIR / "voices-v1.0.bin"

_engine_lock = threading.Lock()
_engine: Any = None
_engine_model_path: Path | None = None
_engine_voices_path: Path | None = None

app = FastAPI(title="Ebook Audio Studio TTS Service")


class SynthesizeRequest(BaseModel):
    text: str = Field(min_length=1)
    output_filename: str = Field(default="preview.wav", min_length=1)
    voice: str = Field(default="af_heart", min_length=1)
    speed: float = Field(default=1.0, ge=0.1, le=4.0)


def _load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Could not parse settings file at %s", SETTINGS_PATH, exc_info=True)
        return {}


def _resolve_model_paths() -> tuple[Path, Path]:
    data = _load_settings()
    model = str(data.get("kokoro_model_path", "") or "").strip()
    voices = str(data.get("kokoro_voices_path", "") or "").strip()
    model_path = Path(model).expanduser().resolve() if model else DEFAULT_MODEL_PATH
    voices_path = Path(voices).expanduser().resolve() if voices else DEFAULT_VOICES_PATH
    return model_path, voices_path


def _health_payload() -> dict[str, Any]:
    model_path, voices_path = _resolve_model_paths()
    models_ready = model_path.exists() and voices_path.exists()
    payload = {
        "status": "ok",
        "models_ready": models_ready,
        "model_path": str(model_path),
        "voices_path": str(voices_path),
    }
    if Kokoro is None:
        payload["status"] = "error"
        payload["models_ready"] = False
        payload["detail"] = "kokoro-onnx is not installed in the TTS service environment."
    return payload


def _ensure_engine() -> Any:
    global _engine, _engine_model_path, _engine_voices_path
    if Kokoro is None:
        raise RuntimeError("kokoro-onnx is not installed")

    model_path, voices_path = _resolve_model_paths()
    if not model_path.exists():
        raise FileNotFoundError(
            f"Kokoro model file not found: {model_path}. Set kokoro_model_path or run model setup."
        )
    if not voices_path.exists():
        raise FileNotFoundError(
            f"Kokoro voices file not found: {voices_path}. Set kokoro_voices_path or run model setup."
        )

    with _engine_lock:
        if (
            _engine is not None
            and _engine_model_path == model_path
            and _engine_voices_path == voices_path
        ):
            return _engine
        try:
            _engine = Kokoro(model_path=str(model_path), voices_path=str(voices_path))
        except TypeError:
            _engine = Kokoro(str(model_path), str(voices_path))
        _engine_model_path = model_path
        _engine_voices_path = voices_path
        return _engine


def _normalize_audio_output(result: Any) -> tuple[np.ndarray, int]:
    if isinstance(result, tuple) and len(result) == 2:
        audio, sample_rate = result
    else:
        audio = result
        sample_rate = 24000
    pcm = np.asarray(audio, dtype=np.float32)
    if pcm.ndim > 1:
        pcm = np.squeeze(pcm)
    if pcm.size == 0:
        raise RuntimeError("Kokoro returned empty audio")
    return pcm, int(sample_rate)


def _synthesize_with_engine(engine: Any, *, text: str, voice: str, speed: float) -> tuple[np.ndarray, int]:
    methods = [getattr(engine, n, None) for n in ("create", "synthesize", "generate")]
    methods = [m for m in methods if callable(m)]
    if not methods:
        raise RuntimeError("Kokoro engine does not expose a synthesis method")

    attempts = (
        {"text": text, "voice": voice, "speed": speed},
        {"text": text, "voice": voice},
        {"text": text, "voice": voice, "rate": speed},
    )
    for method in methods:
        for kwargs in attempts:
            try:
                return _normalize_audio_output(method(**kwargs))
            except TypeError:
                continue
    raise RuntimeError("Unable to call Kokoro synthesis API with supported argument sets")


@app.get("/health")
def health() -> dict[str, Any]:
    return _health_payload()


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest) -> dict[str, Any]:
    try:
        engine = _ensure_engine()
        audio, sample_rate = _synthesize_with_engine(
            engine,
            text=req.text,
            voice=req.voice,
            speed=float(req.speed),
        )
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unhandled synthesize failure")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = Path(req.output_filename).name or "output.wav"
    if not filename.lower().endswith(".wav"):
        filename = f"{filename}.wav"
    output_path = (OUTPUT_DIR / filename).resolve()

    try:
        sf.write(str(output_path), audio, sample_rate)
    except Exception as exc:
        logger.exception("Failed writing synthesized audio")
        raise HTTPException(status_code=500, detail=f"Failed to write audio file: {exc}") from exc

    duration_ms = int((len(audio) / max(sample_rate, 1)) * 1000)
    return {
        "status": "ok",
        "audio_path": str(output_path),
        "sample_rate": sample_rate,
        "duration_ms": duration_ms,
        "voice": req.voice,
        "speed": float(req.speed),
    }
