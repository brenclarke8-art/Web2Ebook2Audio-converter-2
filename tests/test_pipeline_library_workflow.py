from __future__ import annotations

import json

from ebook_app.pipeline_controller import PipelineController


class DummySettings:
    def __init__(self):
        self.data = {
            "output_dir": "output",
            "index_url": "https://example.com/index",
            "tts_backend_mode": "local",
            "tts_backend_url": "http://127.0.0.1:5005",
            "kokoro_model_path": "",
            "kokoro_voices_path": "",
            "tts_speed": 1.0,
            "tts_voice": "af_heart",
            "ollama_url": "http://127.0.0.1:11434/api/generate",
            "ollama_model": "mistral",
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
            "multispeaker_enabled": True,
            "narrator_voice": "af_heart",
            "default_male_voice": "am_adam",
            "default_female_voice": "af_heart",
            "character_review_approved": False,
            "audio_output_mode": "per_chapter",
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
            return [{"url": url, "title": "title", "content": "content"} for url in selected_urls]

    monkeypatch.setattr("ebook_app.pipeline_controller.WebScraper", _FakeScraper)

    controller.scrape_chapters()

    assert captured["urls"] == [
        "https://example.com/book/chapter-2",
        "https://example.com/book/chapter-3",
        "https://example.com/book/chapter-4",
    ]
    assert len(controller.chapters) == 3


def test_run_all_pauses_before_audio_until_review_approved(tmp_path):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    settings.set("character_review_approved", False)
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")

    called = []
    for step in [
        "scrape_index",
        "scrape_chapters",
        "translate_chapters",
        "parse_dialogue",
        "multispeaker_tts",
        "batch_tts",
        "forced_alignment",
        "smil_generation",
        "epub_export",
    ]:
        setattr(controller, step, lambda step_name=step: called.append(step_name))

    controller.run_all()

    assert called == ["scrape_index", "scrape_chapters", "translate_chapters", "parse_dialogue"]
    assert controller.review_required is True
