from __future__ import annotations

import json

from ebook_app.models.dialogue_parser import DetectedCharacter, ParseResult, Segment
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
            "tts_voice": "af_heart",
            "ollama_url": "http://127.0.0.1:11434/api/generate",
            "ollama_model": "mistral",
            "character_confidence_threshold": 0.8,
            "pending_character_additions": [],
            "character_db": [],
            "multispeaker_enabled": True,
            "narrator_voice": "af_heart",
            "default_male_voice": "am_adam",
            "default_female_voice": "af_heart",
        }

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

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

    @property
    def tts_speed(self):
        return self.data["tts_speed"]


def test_parse_dialogue_persists_chapter_info_and_pending_characters(tmp_path, monkeypatch):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")
    controller.translated_chapters = [{"title": "Chapter 1", "content": "Text"}]

    def _fake_parse(self, text, chapter_id="ch"):
        return ParseResult(
            segments=[Segment(text=text, speaker="narrator", type="narration", gender="unknown")],
            detected_characters=[
                DetectedCharacter(name="Alice", gender="female", confidence=0.91),
                DetectedCharacter(name="Bob", gender="male", confidence=0.60),
            ],
        )

    monkeypatch.setattr("ebook_app.models.dialogue_parser.DialogueParser.parse", _fake_parse)
    controller.parse_dialogue()

    chapter_info = tmp_path / "pipeline_work" / "ch000" / "chapter_info.json"
    assert chapter_info.exists()
    with chapter_info.open(encoding="utf-8") as handle:
        data = json.load(handle)
    assert data["segments"][0]["type"] == "narration"

    pending = settings.get("pending_character_additions", [])
    assert [item["name"] for item in pending] == ["Alice"]


def test_multispeaker_tts_uses_character_db_and_default_voices(tmp_path):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    settings.set(
        "character_db",
        [{"name": "Alice", "voice": "bf_emma", "gender": "female", "description": ""}],
    )
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")
    controller.dialogue_segments = {
        0: [
            Segment(text="Hi", type="dialogue", speaker="Alice", gender="female"),
            Segment(text="Hello", type="dialogue", speaker="Guard", gender="male"),
        ]
    }

    captured = {}

    class FakeEngine:
        def generate_multi_voice_audio(self, **kwargs):
            captured.update(kwargs)
            out = tmp_path / "pipeline_work" / "audio" / kwargs["output_filename"]
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"wav")
            return out

    controller._make_tts_backend = lambda output_dir=None: FakeEngine()  # type: ignore[assignment]
    controller.multispeaker_tts()

    assert captured["voice_mappings"]["Alice"] == "bf_emma"
    assert captured["voice_mappings"]["narrator"] == "af_heart"
    assert captured["default_male_voice"] == "am_adam"
    assert captured["default_female_voice"] == "af_heart"
