from __future__ import annotations

import json

from ebook_app.models.dialogue_parser import DetectedCharacter, ParseResult, Segment
from ebook_app.pipeline_controller import PipelineController


class DummySettings:
    def __init__(self):
        self.data = {
            "output_dir": "output",
            "tts_backend_url": "http://127.0.0.1:5005",
            "kokoro_model_path": "",
            "kokoro_voices_path": "",
            "tts_speed": 1.0,
            "tts_voice": "af_heart",
            "dialogue_llm_url": "http://127.0.0.1:11434/api/chat",
            "dialogue_llm_model": "mistral:instruct",
            "dialogue_llm_mode": "full",
            "dialogue_llm_timeout": 120,
            "dialogue_llm_retries": 1,
            "dialogue_llm_strict_quotes": False,
            "llm_preflight_check": False,
            "character_confidence_threshold": 0.8,
            "pending_character_additions": [],
            "character_db": [],
            "narrator_voice": "af_heart",
            "default_male_voice": "am_adam",
            "default_female_voice": "af_heart",
            "speaker_conf_threshold": 0.8,
            "character_conf_threshold": 0.8,
        }

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    @property
    def output_dir(self):
        return self.data["output_dir"]

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


def test_llm_semantic_analysis_persists_raw_and_chapter_info(tmp_path, monkeypatch):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")

    chapters = [{"title": "Chapter 1", "content": "Text"}]
    work_dir = tmp_path / "pipeline_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "chapters.json").write_text(json.dumps(chapters), encoding="utf-8")
    (work_dir / "clean_review_plan.json").write_text(json.dumps({"needs_review": []}), encoding="utf-8")
    (work_dir / "ch1_cleaned.txt").write_text("Text", encoding="utf-8")

    def _fake_parse(self, text, chapter_id="ch"):
        return ParseResult(
            segments=[Segment(text=text, speaker="narrator", type="narration", gender="unknown")],
            detected_characters=[
                DetectedCharacter(name="Alice", gender="female", confidence=0.91),
                DetectedCharacter(name="Bob", gender="male", confidence=0.60),
            ],
        )

    monkeypatch.setattr("ebook_app.models.dialogue_parser.DialogueParser.parse", _fake_parse)
    controller.llm_semantic_analysis()

    raw_path = work_dir / "ch1_llm_raw.json"
    chapter_info = work_dir / "ch1" / "ch1_chapter_info.json"

    assert raw_path.exists()
    assert chapter_info.exists()

    with chapter_info.open(encoding="utf-8") as handle:
        data = json.load(handle)

    assert data["segments"][0]["type"] == "narration"
    assert [item["name"] for item in data["detected_characters"]] == ["Alice", "Bob"]


def test_write_final_chapter_files_assigns_known_and_default_voices(tmp_path):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")

    character_db = [{"name": "Alice", "voice": "bf_emma", "gender": "female", "description": ""}]

    controller._write_final_chapter_files(
        chapter_id="ch1",
        segments=[
            {"text": "Hi", "type": "dialogue", "speaker": "Alice", "gender": "female"},
            {"text": "Hello", "type": "dialogue", "speaker": "Guard", "gender": "male"},
        ],
        detected_chars=[
            {"name": "Alice", "gender": "female", "confidence": 0.9},
            {"name": "Guard", "gender": "male", "confidence": 0.9},
        ],
        narrator_voice="af_heart",
        default_male="am_adam",
        default_female="af_heart",
        character_db=character_db,
    )

    with (tmp_path / "pipeline_work" / "ch1_characters_final.json").open(encoding="utf-8") as handle:
        final_chars = json.load(handle)

    assert final_chars[0]["voice"] == "bf_emma"
    assert final_chars[1]["voice"] == "am_adam"
    assert any(char["name"] == "Guard" and char["voice"] == "am_adam" for char in character_db)
