from __future__ import annotations

import json
from types import SimpleNamespace

from ebook_app.pipeline.controller import PipelineController


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
            "llm_provider": "ollama_local",
            "llm_url": "http://127.0.0.1:11434/api/chat",
            "llm_model": "mistral:instruct",
            "llm_api_key": "",
            "dialogue_llm_url": "http://127.0.0.1:11434/api/chat",
            "dialogue_llm_model": "mistral:instruct",
            "dialogue_llm_timeout": 120,
            "dialogue_llm_retries": 1,
            "dialogue_llm_strict_quotes": False,
            "llm_preflight_check": False,
            "phase1_llm_assist_enabled": False,
            "phase2_batch_size": 20,
            "json_pipeline_enabled": True,
            "json_repair_max_retries": 2,
            "llm_segment_mode": "batch",
            "llm_fallback_failure_threshold": 2,
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

    monkeypatch.setattr("ebook_app.pipeline.controller.WebScraper", _FakeScraper)

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


def test_pipeline_controller_applies_configured_llm_timeout_and_retries(tmp_path):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    settings.set("dialogue_llm_timeout", 345)
    settings.set("dialogue_llm_retries", 0)

    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")

    assert controller.llm_client.timeout == 345
    assert controller.llm_client.retries == 0


def test_pipeline_controller_applies_json_pipeline_settings(tmp_path):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    settings.set("json_pipeline_enabled", False)
    settings.set("json_repair_max_retries", 1)
    settings.set("llm_segment_mode", "single")
    settings.set("llm_fallback_failure_threshold", 5)

    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")

    assert controller.pass2_classifier.json_pipeline_enabled is False
    assert controller.pass2_classifier.json_repair_max_retries == 1
    assert controller.pass2_classifier.segment_mode == "single"
    assert controller.pass2_classifier.fallback_failure_threshold == 5


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

    monkeypatch.setattr("ebook_app.pipeline.controller.WebScraper", _FakeScraper)

    controller.scrape_chapters()

    assert captured["urls"] == [
        "https://example.com/book/chapter-2",
        "https://example.com/book/chapter-3",
        "https://example.com/book/chapter-4",
    ]
    assert len(controller.chapters) == 3
    assert (tmp_path / "pipeline_work" / "ch2_raw.txt").read_text(encoding="utf-8") == "content for 2"
    assert (tmp_path / "pipeline_work" / "ch4_raw.txt").read_text(encoding="utf-8") == "content for 4"


def test_scrape_chapters_fallback_applies_selected_range(tmp_path, monkeypatch):
    """scrape_chapters falls back to chapters_raw.json and must still honour the range."""
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    work_dir = tmp_path / "pipeline_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    controller = PipelineController(settings=settings, work_dir=work_dir)
    # chapter_urls is intentionally empty to trigger the fallback branch
    controller.chapter_urls = []
    controller.set_chapter_range(2, 4)

    chapters_raw = [
        {"title": f"Chapter {i + 1}", "source": f"https://example.com/book/chapter-{i + 1}"}
        for i in range(5)
    ]
    (work_dir / "chapters_raw.json").write_text(
        json.dumps(chapters_raw), encoding="utf-8"
    )

    captured = {}

    class _FakeScraper:
        def scrape_chapters(self, selected_urls):
            captured["urls"] = selected_urls
            return [
                {"url": url, "title": "title", "content": f"content {idx + 2}"}
                for idx, url in enumerate(selected_urls)
            ]

    monkeypatch.setattr("ebook_app.pipeline.controller.WebScraper", _FakeScraper)

    controller.scrape_chapters()

    assert captured["urls"] == [
        "https://example.com/book/chapter-2",
        "https://example.com/book/chapter-3",
        "https://example.com/book/chapter-4",
    ]
    assert len(controller.chapters) == 3


def test_run_all_executes_new_pipeline_steps_in_order(tmp_path):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")

    called = []
    for step in controller.STEPS:
        setattr(controller, step, lambda step_name=step: called.append(step_name))

    controller.run_all()

    assert called == controller.STEPS


def test_build_dialogue_parser_prefers_unified_model_setting(tmp_path):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    settings.set("llm_model", "unified:model")
    settings.set("dialogue_llm_model", "legacy:model")
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")

    parser = controller._build_dialogue_parser()

    assert parser.model == "unified:model"
    assert parser.semantic_model == "unified:model"
    assert parser.fallback_model == "unified:model"
    assert parser.formatter_model == "unified:model"


def test_build_dialogue_parser_applies_delimiter_and_batch_settings(tmp_path):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    settings.set("dialogue_llm_delimited_text_only", True)
    settings.set("dialogue_llm_delimiter_double_quotes", False)
    settings.set("dialogue_llm_delimiter_single_quotes", True)
    settings.set("llm_chunk_size", 321)
    settings.set("llm_chunk_overlap", 12)
    settings.set("dialogue_llm_batch_size", 3)
    settings.set("dialogue_llm_protocol_retries", 2)
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")

    parser = controller._build_dialogue_parser()

    assert parser.delimited_text_only is True
    assert parser.delimiter_filters["double_quotes"] is False
    assert parser.delimiter_filters["single_quotes"] is True
    assert parser.chunk_size == 321
    assert parser.chunk_overlap == 12
    assert parser.pass2_batch_size == 3
    assert parser.protocol_retries == 2


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


def test_pass2_classification_outputs_required_segment_schema(tmp_path, monkeypatch):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    settings.set("phase2_batch_size", 2)
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")

    work_dir = tmp_path / "pipeline_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "chapters_raw.json").write_text(
        json.dumps([{"title": "Chapter 1"}]),
        encoding="utf-8",
    )
    (work_dir / "ch1_pass1.json").write_text(
        json.dumps(
            {
                "chapter_id": "ch1",
                "segments": [
                    {
                        "text": "“Hello there.”",
                        "paragraph_id": "ch1_p000",
                        "context_before": "Before",
                        "context_after": "After",
                        "is_dialogue_candidate": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        controller.pass2_classifier,
        "classify_segments",
        lambda segments, chapter_id="": [
            {
                "text": segments[0]["text"],
                "type": "dialogue",
                "speaker": "Alice",
                "gender": "female",
                "speaker_confidence": 0.9,
                "gender_confidence": 0.8,
                "character_confidence": 0.85,
                "paragraph_id": "ch1_p000",
                "voice": "af_heart",
                "emotion": "happy",
                "prior_segment_text": "Before",
                "next_segment_text": "After",
            }
        ],
    )

    controller.pass2_classification()
    out = json.loads((work_dir / "ch1_pass2.json").read_text(encoding="utf-8"))
    segment = out["segments"][0]
    assert set(segment.keys()) == {
        "text",
        "type",
        "speaker",
        "gender",
        "speaker_confidence",
        "gender_confidence",
        "character_confidence",
        "paragraph_id",
        "voice",
        "emotion",
        "prior_segment_text",
        "next_segment_text",
    }


def test_pass1_extraction_applies_optional_llm_assist(tmp_path, monkeypatch):
    settings = DummySettings()
    settings.set("output_dir", str(tmp_path))
    settings.set("phase1_llm_assist_enabled", True)
    controller = PipelineController(settings=settings, work_dir=tmp_path / "pipeline_work")

    work_dir = tmp_path / "pipeline_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "chapters_raw.json").write_text(
        json.dumps([{"title": "Chapter 1"}]),
        encoding="utf-8",
    )
    (work_dir / "ch1_cleaned.txt").write_text("Paragraph one.\n\nParagraph two.", encoding="utf-8")

    monkeypatch.setattr(
        controller.pass2_classifier,
        "assist_pass1_segments",
        lambda segments, chapter_id="": [{**segment, "is_dialogue_candidate": True} for segment in segments],
    )

    controller.pass1_extraction()
    out = json.loads((work_dir / "ch1_pass1.json").read_text(encoding="utf-8"))
    assert out["segments"][0]["is_dialogue_candidate"] is True


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
