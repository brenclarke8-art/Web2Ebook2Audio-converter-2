from __future__ import annotations

from pathlib import Path

import pytest

from ebook_app.services import kokoro_model_setup


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload
        self.chunk_size_seen: int | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self) -> None:
        pass

    def iter_content(self, chunk_size: int = 1024):
        self.chunk_size_seen = chunk_size
        yield self._payload


def test_download_and_setup_kokoro_models_writes_default_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kokoro_model_setup, "DEFAULT_MODELS_DIR", tmp_path)
    responses: list[_FakeResponse] = []
    seen_urls: list[str] = []

    def fake_get(url: str, stream: bool, timeout: int):
        assert stream is True
        assert timeout == 120
        seen_urls.append(url)
        response = _FakeResponse(url.encode("utf-8"))
        responses.append(response)
        return response

    monkeypatch.setattr(kokoro_model_setup.requests, "get", fake_get)

    result = kokoro_model_setup.download_and_setup_kokoro_models()

    model_path = tmp_path / kokoro_model_setup.MODEL_FILENAME
    voices_path = tmp_path / kokoro_model_setup.VOICES_FILENAME
    assert result["model_path"] == str(model_path)
    assert result["voices_path"] == str(voices_path)
    assert model_path.exists()
    assert voices_path.exists()
    assert len(responses) == 2
    assert seen_urls == [
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
        "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
    ]
    assert all(
        r.chunk_size_seen == kokoro_model_setup._DOWNLOAD_CHUNK_SIZE for r in responses
    )


def test_download_and_setup_kokoro_models_wraps_request_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kokoro_model_setup, "DEFAULT_MODELS_DIR", tmp_path)

    def fake_get(url: str, stream: bool, timeout: int):
        raise kokoro_model_setup.requests.RequestException("network down")

    monkeypatch.setattr(kokoro_model_setup.requests, "get", fake_get)

    with pytest.raises(RuntimeError, match="Failed to download Kokoro model file"):
        kokoro_model_setup.download_and_setup_kokoro_models()
