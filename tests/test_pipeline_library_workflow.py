from __future__ import annotations

import json
from types import SimpleNamespace

from ebook_app.pipeline_controller import PipelineController


class DummySettings:
    def __init__(self):
        self.data = {
            "output_dir": "output",
            "index_url": "https://example.com/index",
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
            "clean_review_mode": "semi",
            "clean_review_sample_chapters": 3,
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


def test_scrape_index_filters_placeholder_urls(tmp_path, monkeypatch):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")

    urls = [
        "https://example.com/book/chapter-1",
        "https://example.com/book/paywalled-chapter-2",
        "https://example.com/book/chapter-3",
    ]
    class _FakeScraper:
        def scrape_index_page(self, _url):
            return urls

    monkeypatch.setattr("ebook_app.pipeline_controller.WebScraper", _FakeScraper)

    controller.scrape_index()

    assert len(controller.raw_chapter_urls) == 3
    assert len(controller.chapter_urls) == 2
    assert controller.chapter_urls == [
        "https://example.com/book/chapter-1",
        "https://example.com/book/chapter-3",
    ]

    with open(tmp_path / "pipeline_work" / "raw_chapter_urls.json", encoding="utf-8") as f:
        assert len(json.load(f)) == 3
    with open(tmp_path / "pipeline_work" / "chapter_urls.json", encoding="utf-8") as f:
        assert len(json.load(f)) == 2


def test_scrape_chapters_uses_selected_range(tmp_path, monkeypatch):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")
    controller.chapter_urls = [
        "https://example.com/book/chapter-1",
        "https://example.com/book/chapter-2",
        "https://example.com/book/chapter-3",
        "https://example.com/book/chapter-4",
        "https://example.com/book/chapter-5",
    ]
    controller.set_chapter_range(2, 4)

    captured = {}

    class _FakeScraper:
        def scrape_chapters(self, selected_urls):
            captured["urls"] = selected_urls
            return [
                {"url": url, "title": "title", "content": f"content for {idx + 2}"}
                for idx, url in enumerate(selected_urls)
            ]

    monkeypatch.setattr("ebook_app.pipeline_controller.WebScraper", _FakeScraper)

    controller.scrape_chapters()

    assert captured["urls"] == [
        "https://example.com/book/chapter-2",
        "https://example.com/book/chapter-3",
        "https://example.com/book/chapter-4",
    ]
    assert len(controller.chapters) == 3
    assert (tmp_path / "pipeline_work" / "ch2_raw.txt").read_text(encoding="utf-8") == "content for 2"
    assert (tmp_path / "pipeline_work" / "ch4_raw.txt").read_text(encoding="utf-8") == "content for 4"


def test_run_all_executes_new_pipeline_steps_in_order(tmp_path):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")

    called = []
    for step in controller.STEPS:
        setattr(controller, step, lambda step_name=step: called.append(step_name))

    controller.run_all()

    assert called == controller.STEPS


def test_clean_chapters_removes_ui_noise_and_zero_width_chars(tmp_path):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")
    controller.chapters = [
        {
            "title": "Chapter 1",
            "content": "Next Chapter\nSubscribe now\nLine\u200B one.\n\nLine two.",
        }
    ]

    controller.clean_chapters()

    cleaned = (tmp_path / "pipeline_work" / "ch1_cleaned.txt").read_text(encoding="utf-8")
    assert "Next Chapter" not in cleaned
    assert "Subscribe now" not in cleaned
    assert "\u200B" not in cleaned
    assert "Line one." in cleaned
    assert "Line two." in cleaned


def test_tts_generate_stops_when_controller_is_cancelled(tmp_path, monkeypatch):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")
    controller.start()
    controller.chapters = [{"title": "Chapter 1"}]
    (tmp_path / "pipeline_work" / "chapters.json").write_text(
        json.dumps(controller.chapters),
        encoding="utf-8",
    )
    (tmp_path / "pipeline_work" / "ch1_chapter_info_final.json").write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "text": "line",
                        "type": "dialogue",
                        "speaker": "Alice",
                        "gender": "female",
                        "paragraph_id": "ch1_p0",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class _FakeEngine:
        def generate_audio(self, **_kwargs):
            controller.stop()
            return None

        def get_last_audio_duration(self):
            return 0.0

        def concatenate_audio_files(self, files, output_path):
            output_path.write_bytes(b"")

    monkeypatch.setattr(controller, "_make_tts_backend", lambda output_dir=None: _FakeEngine())

    controller.tts_generate()

    assert not (tmp_path / "pipeline_work" / "audio_timing.json").exists()


def test_recheck_dialogue_with_manual_context_overwrites_llm_files(tmp_path, monkeypatch):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")
    controller.set_chapter_range(1, 1)
    (tmp_path / "pipeline_work" / "chapters.json").write_text(
        json.dumps([{"title": "Chapter A"}]),
        encoding="utf-8",
    )
    (tmp_path / "pipeline_work" / "ch1_cleaned.txt").write_text("Hello there.", encoding="utf-8")

    fake_result = SimpleNamespace(
        segments=[
            SimpleNamespace(
                text="Hello there.",
                type="dialogue",
                speaker="Alice",
                gender="female",
                speaker_confidence=1.0,
                gender_confidence=1.0,
                character_confidence=1.0,
                paragraph_id="ch1_p0",
            )
        ],
        detected_characters=[SimpleNamespace(name="Alice", gender="female", confidence=1.0)],
    )

    class _FakeParser:
        def parse(self, text, chapter_id, manual_segment_hints=None):
            assert chapter_id == "ch1"
            assert text == "Hello there."
            assert manual_segment_hints == [
                {"text": "Hello there.", "speaker": "Alice", "type": "dialogue"}
            ]
            return fake_result

    monkeypatch.setattr(controller, "_build_dialogue_parser", lambda: _FakeParser())

    result = controller.recheck_dialogue_with_manual_context(
        "ch1",
        [{"text": "Hello there.", "speaker": "Alice", "type": "dialogue"}],
    )

    assert result == {"chapter_id": "ch1", "segment_count": 1, "character_count": 1}
    raw = json.loads((tmp_path / "pipeline_work" / "ch1_llm_raw.json").read_text(encoding="utf-8"))
    normalized = json.loads(
        (tmp_path / "pipeline_work" / "ch1_llm_normalized.json").read_text(encoding="utf-8")
    )
    assert raw["segments"][0]["speaker"] == "Alice"
    assert normalized["segments"][0]["type"] == "dialogue"
