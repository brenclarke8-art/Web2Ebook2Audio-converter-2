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
_DOWNLOAD_CHUNK_SIZE = 1024 * 1024
_REQUEST_TIMEOUT_SECONDS = 120


def resolve_kokoro_model_paths() -> tuple[Path, Path]:
    return DEFAULT_MODELS_DIR / MODEL_FILENAME, DEFAULT_MODELS_DIR / VOICES_FILENAME


def _download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(f"{destination.name}.tmp")
    try:
        with requests.get(url, stream=True, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            response.raise_for_status()
            with temp_path.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=_DOWNLOAD_CHUNK_SIZE):
                    if chunk:
                        fh.write(chunk)
        temp_path.replace(destination)
    except requests.RequestException as exc:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Download failed for {destination.name} from {url}: {exc}"
        ) from exc
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"File write failed for {destination}: {exc}") from exc


def download_and_setup_kokoro_models() -> dict[str, str]:
    model_path, voices_path = resolve_kokoro_model_paths()
    try:
        _download_file(_MODEL_URL, model_path)
    except RuntimeError as exc:
        raise RuntimeError(
            f"Failed to set up Kokoro model file ({MODEL_FILENAME}): {exc}"
        ) from exc
    try:
        _download_file(_VOICES_URL, voices_path)
    except RuntimeError as exc:
        raise RuntimeError(
            f"Failed to set up Kokoro voices file ({VOICES_FILENAME}): {exc}"
        ) from exc
    return {
        "model_path": str(model_path),
        "voices_path": str(voices_path),
    }
