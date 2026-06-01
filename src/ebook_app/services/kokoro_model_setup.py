from __future__ import annotations

from pathlib import Path

import requests

from ebook_app.core.settings_manager import APP_HOME_DIR

MODEL_FILENAME = "kokoro-v1.0.onnx"
VOICES_FILENAME = "voices-v1.0.bin"
DEFAULT_MODELS_DIR = APP_HOME_DIR / "models"

_MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/kokoro-v1.0.onnx"
)
_VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/voices-v1.0.bin"
)


def resolve_kokoro_model_paths() -> tuple[Path, Path]:
    return DEFAULT_MODELS_DIR / MODEL_FILENAME, DEFAULT_MODELS_DIR / VOICES_FILENAME


def _download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(f"{destination.name}.tmp")
    try:
        with requests.get(url, stream=True, timeout=120) as response:
            response.raise_for_status()
            with temp_path.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        fh.write(chunk)
        temp_path.replace(destination)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def download_and_setup_kokoro_models() -> dict[str, str]:
    model_path, voices_path = resolve_kokoro_model_paths()
    try:
        _download_file(_MODEL_URL, model_path)
        _download_file(_VOICES_URL, voices_path)
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to download Kokoro model files: {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"Failed to write Kokoro model files: {exc}") from exc
    return {
        "model_path": str(model_path),
        "voices_path": str(voices_path),
    }
