from __future__ import annotations

import pytest

from ebook_app.models.dialogue_parser import DialogueParser
from ebook_app.pipeline_controller import PipelineController


class DummySettings:
    def __init__(self):
        self.data = {
            "output_dir": "output",
            "tts_backend_mode": "local",
            "tts_backend_url": "http://127.0.0.1:5005",
            "kokoro_model_path": "",
            "kokoro_voices_path": "",
            "tts_speed": 1.0,
        }

    def get(self, key, default=None):
        return self.data.get(key, default)

    @property
    def output_dir(self):
        return self.data["output_dir"]

    @property
    def tts_backend_mode(self):
        return self.data["tts_backend_mode"]

    @property
    def tts_backend_url(self):
        return self.data["tts_backend_url"]

    @property
    def kokoro_model_path(self):
        return self.data["kokoro_model_path"]

    @property
    def kokoro_voices_path(self):
        return self.data["kokoro_voices_path"]


class _Response:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_preflight_fails_when_model_missing(monkeypatch, tmp_path):
    controller = PipelineController(settings=DummySettings(), work_dir=tmp_path / "pipeline_work")
    parser = DialogueParser(ollama_url="http://127.0.0.1:11434/api/chat", model="mistral:instruct")

    def _fake_get(*_args, **_kwargs):
        return _Response({"models": [{"name": "llama3:latest"}]})

    monkeypatch.setattr("requests.get", _fake_get)

    with pytest.raises(RuntimeError, match="not installed"):
        controller._preflight_llm_check(parser)


def test_preflight_accepts_installed_model(monkeypatch, tmp_path):
    controller = PipelineController(settings=DummySettings(), work_dir=tmp_path / "pipeline_work")
    parser = DialogueParser(ollama_url="http://127.0.0.1:11434/api/chat", model="mistral:instruct")

    def _fake_get(*_args, **_kwargs):
        return _Response({"models": [{"name": "mistral:instruct"}]})

    monkeypatch.setattr("requests.get", _fake_get)
    controller._preflight_llm_check(parser)
