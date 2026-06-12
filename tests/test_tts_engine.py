from __future__ import annotations

from pathlib import Path

import pytest
import requests

from ebook_app.tts.tts_service import TTSEngine


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self) -> dict:
        return self._payload


def test_generate_audio_retries_once_on_503_and_succeeds(tmp_path, monkeypatch):
    src_audio = tmp_path / "server.wav"
    src_audio.write_bytes(b"RIFF")
    out_dir = tmp_path / "out"

    responses = [
        _FakeResponse(503),
        _FakeResponse(
            200,
            {
                "audio_path": str(src_audio),
                "duration_ms": 2500,
            },
        ),
    ]
    calls: list[dict] = []

    def _fake_post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return responses.pop(0)

    monkeypatch.setattr("ebook_app.tts.tts_service.requests.post", _fake_post)
    monkeypatch.setattr("ebook_app.tts.tts_service.time.sleep", lambda *_: None)

    engine = TTSEngine(output_dir=out_dir, retry_attempts=3, retry_backoff_sec=0)
    output_path = engine.generate_audio(
        text="hello",
        output_filename="test.wav",
        voice="af_heart",
        speed=1.0,
    )

    assert len(calls) == 2
    assert output_path == out_dir / "test.wav"
    assert output_path.read_bytes() == b"RIFF"
    assert engine.get_last_audio_duration() == 2.5


def test_generate_audio_raises_after_retry_budget_exhausted(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    attempts = 3
    calls = 0

    def _always_503(url, json, timeout):
        nonlocal calls
        calls += 1
        return _FakeResponse(503)

    monkeypatch.setattr("ebook_app.tts.tts_service.requests.post", _always_503)
    monkeypatch.setattr("ebook_app.tts.tts_service.time.sleep", lambda *_: None)

    engine = TTSEngine(output_dir=out_dir, retry_attempts=attempts, retry_backoff_sec=0)
    with pytest.raises(requests.HTTPError):
        engine.generate_audio(
            text="hello",
            output_filename="test.wav",
            voice="af_heart",
            speed=1.0,
        )

    assert calls == attempts


def test_generate_audio_does_not_retry_non_retryable_503(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    calls = 0

    def _always_missing_model(url, json, timeout):
        nonlocal calls
        calls += 1
        return _FakeResponse(503, {"detail": "Kokoro model file not found: /missing/model.onnx"})

    monkeypatch.setattr("ebook_app.tts.tts_service.requests.post", _always_missing_model)
    monkeypatch.setattr("ebook_app.tts.tts_service.time.sleep", lambda *_: None)

    engine = TTSEngine(output_dir=out_dir, retry_attempts=3, retry_backoff_sec=0)
    with pytest.raises(requests.HTTPError):
        engine.generate_audio(
            text="hello",
            output_filename="test.wav",
            voice="af_heart",
            speed=1.0,
        )

    assert calls == 1
