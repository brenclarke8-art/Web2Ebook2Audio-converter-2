from __future__ import annotations

from pathlib import Path

import pytest

from ebook_app.services import kokoro_model_setup


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int = 1024):
        yield self._payload


def test_download_and_setup_kokoro_models_writes_default_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kokoro_model_setup, "DEFAULT_MODELS_DIR", tmp_path)

    def fake_get(url: str, stream: bool, timeout: int):
        assert stream is True
        assert timeout == 120
        return _FakeResponse(url.encode("utf-8"))

    monkeypatch.setattr(kokoro_model_setup.requests, "get", fake_get)

    result = kokoro_model_setup.download_and_setup_kokoro_models()

    model_path = tmp_path / kokoro_model_setup.MODEL_FILENAME
    voices_path = tmp_path / kokoro_model_setup.VOICES_FILENAME
    assert result["model_path"] == str(model_path)
    assert result["voices_path"] == str(voices_path)
    assert model_path.exists()
    assert voices_path.exists()


def test_download_and_setup_kokoro_models_wraps_request_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kokoro_model_setup, "DEFAULT_MODELS_DIR", tmp_path)

    def fake_get(url: str, stream: bool, timeout: int):
        raise kokoro_model_setup.requests.RequestException("network down")

    monkeypatch.setattr(kokoro_model_setup.requests, "get", fake_get)

    with pytest.raises(RuntimeError, match="Failed to download Kokoro model files"):
        kokoro_model_setup.download_and_setup_kokoro_models()
