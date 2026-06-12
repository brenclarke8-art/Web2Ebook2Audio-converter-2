from __future__ import annotations

import sys
import types
import json
from types import ModuleType, SimpleNamespace


class _DummyQThread:
    def __init__(self, *args, **kwargs) -> None:
        pass


class _DummyWidget:
    def __init__(self, *args, **kwargs) -> None:
        pass


class _DummyMessageBox:
    @staticmethod
    def information(*args, **kwargs) -> None:
        pass


sys.modules.setdefault("PySide6", ModuleType("PySide6"))
qtcore = ModuleType("PySide6.QtCore")
qtcore.QThread = _DummyQThread
qtcore.Signal = lambda *args, **kwargs: None
sys.modules["PySide6.QtCore"] = qtcore

qtwidgets = ModuleType("PySide6.QtWidgets")
for name in [
    "QCheckBox",
    "QComboBox",
    "QFormLayout",
    "QGroupBox",
    "QHeaderView",
    "QHBoxLayout",
    "QLabel",
    "QLineEdit",
    "QProgressBar",
    "QPushButton",
    "QSplitter",
    "QSpinBox",
    "QTabWidget",
    "QTableWidget",
    "QTableWidgetItem",
    "QTextEdit",
    "QVBoxLayout",
    "QWidget",
]:
    setattr(qtwidgets, name, _DummyWidget)
qtwidgets.QMessageBox = _DummyMessageBox
sys.modules["PySide6.QtWidgets"] = qtwidgets

base_page = ModuleType("ebook_app.app.ui.base_view")
base_page.BasePage = type("BasePage", (), {})
sys.modules["ebook_app.app.ui.base_view"] = base_page

import ebook_app.app.ui.pipeline_view as pipeline_page_module
from ebook_app.app.ui.pipeline_view import PipelinePage, QMessageBox, _PipelineWorker


class _DeletedWorker:
    def isRunning(self) -> bool:
        raise RuntimeError("libshiboken: Internal C++ object already deleted.")


class _LogCapture:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def log(self, message: str, level: str = "INFO") -> None:
        self.messages.append((message, level))


class _SignalCapture:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def emit(self, *args) -> None:
        self.calls.append(args)


def test_is_busy_ignores_deleted_qt_worker() -> None:
    page = SimpleNamespace(_worker=_DeletedWorker())

    assert PipelinePage._is_busy(page) is False
    assert page._worker is None


def test_on_worker_finished_clears_worker_reference(monkeypatch) -> None:
    button_states: list[bool] = []
    dialogs: list[tuple[str, str]] = []
    log = _LogCapture()
    last_processed: list[int] = []
    reload_calls = {"count": 0}

    def _reload() -> None:
        reload_calls["count"] += 1

    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, title, text: dialogs.append((title, text)),
    )

    page = SimpleNamespace(
        _worker=SimpleNamespace(_end=7),
        project_manager=SimpleNamespace(
            set_last_processed_chapter=lambda chapter: last_processed.append(chapter)
        ),
        _set_buttons_enabled=lambda enabled: button_states.append(enabled),
        _load_active_project_state=_reload,
        _refresh_review_data=lambda: None,
        _tabs=SimpleNamespace(setCurrentIndex=lambda _idx: None),
        log=log,
    )

    PipelinePage._on_worker_finished(page, _PipelineWorker.RUN_TO_REVIEW, "Done")

    assert page._worker is None
    assert button_states == [True]
    assert last_processed == [7]
    assert reload_calls["count"] == 1
    assert log.messages == [("Done", "SUCCESS")]
    assert dialogs == [
        (
            "Character Review Required",
            "Chapter parsing is complete. Review scraped text and detected "
            "characters in the Review tab, then click 'Continue Audio + Export'.",
        )
    ]


def test_run_to_review_reuses_cached_index_inventory(tmp_path) -> None:
    worker = _PipelineWorker(
        project_manager=SimpleNamespace(
            get_chapter_urls=lambda: ["u1", "u2", "u3"],
            get_inventory=lambda: {"raw_chapter_count": 5, "valid_chapter_count": 3},
        ),
        settings=SimpleNamespace(),
        mode=_PipelineWorker.RUN_TO_REVIEW,
        start_ch=1,
        end_ch=2,
    )
    worker.log_message = _SignalCapture()
    worker.inventory_ready = _SignalCapture()
    worker.finished_ok = _SignalCapture()
    worker.failed = _SignalCapture()

    review_plan = tmp_path / "semantic_review_plan.json"
    review_plan.write_text('{"needs_review": []}', encoding="utf-8")

    calls: list[str] = []

    ctrl = SimpleNamespace(
        work_dir=tmp_path,
        chapter_urls=[],
        scrape_index=lambda: calls.append("scrape_index"),
        scrape_chapters=lambda: calls.append("scrape_chapters"),
        pass1_extraction=lambda: calls.append("pass1_extraction"),
        pass2_classification=lambda: calls.append("pass2_classification"),
        smart_review_dialogue=lambda: calls.append("smart_review_dialogue"),
    )

    worker._run_to_review(ctrl)

    assert "scrape_index" not in calls
    assert worker.inventory_ready.calls == [({"raw_count": 5, "valid_count": 3, "chapter_urls": ["u1", "u2", "u3"]},)]
    assert worker.failed.calls == []
    assert worker.finished_ok.calls == [
        (
            _PipelineWorker.RUN_TO_REVIEW,
            "Processing complete. Review detected characters in the Review tab before audio.",
        )
    ]


def test_run_to_review_cached_index_falls_back_raw_count_when_missing(tmp_path) -> None:
    worker = _PipelineWorker(
        project_manager=SimpleNamespace(
            get_chapter_urls=lambda: ["u1", "u2"],
            get_inventory=lambda: {"valid_chapter_count": 99},
        ),
        settings=SimpleNamespace(),
        mode=_PipelineWorker.RUN_TO_REVIEW,
        start_ch=1,
        end_ch=1,
    )
    worker.log_message = _SignalCapture()
    worker.inventory_ready = _SignalCapture()
    worker.finished_ok = _SignalCapture()
    worker.failed = _SignalCapture()

    (tmp_path / "semantic_review_plan.json").write_text('{"needs_review": []}', encoding="utf-8")

    ctrl = SimpleNamespace(
        work_dir=tmp_path,
        chapter_urls=[],
        scrape_index=lambda: None,
        scrape_chapters=lambda: None,
        pass1_extraction=lambda: None,
        pass2_classification=lambda: None,
        smart_review_dialogue=lambda: None,
    )

    worker._run_to_review(ctrl)

    assert worker.inventory_ready.calls == [({"raw_count": 2, "valid_count": 2, "chapter_urls": ["u1", "u2"]},)]
    assert worker.failed.calls == []


def test_run_to_review_scrapes_index_when_cache_missing(tmp_path) -> None:
    import json as _json

    # Write chapters_raw.json that scrape_index would produce
    chapters_raw = tmp_path / "chapters_raw.json"
    chapters_raw.write_text(
        _json.dumps([{"title": "Ch 1", "source": "http://example.com/ch1"}]),
        encoding="utf-8",
    )

    worker = _PipelineWorker(
        project_manager=SimpleNamespace(
            get_chapter_urls=lambda: [],
            get_inventory=lambda: {"raw_chapter_count": 0, "valid_chapter_count": 0},
            get_work_dir=lambda: tmp_path,
        ),
        settings=SimpleNamespace(),
        mode=_PipelineWorker.RUN_TO_REVIEW,
        start_ch=1,
        end_ch=1,
    )
    worker.log_message = _SignalCapture()
    worker.inventory_ready = _SignalCapture()
    worker.finished_ok = _SignalCapture()
    worker.failed = _SignalCapture()

    calls: list[str] = []

    ctrl = SimpleNamespace(
        work_dir=tmp_path,
        scrape_index=lambda: calls.append("scrape_index"),
        scrape_chapters=lambda: calls.append("scrape_chapters"),
        pass1_extraction=lambda: calls.append("pass1_extraction"),
        pass2_classification=lambda: calls.append("pass2_classification"),
        smart_review_dialogue=lambda: calls.append("smart_review_dialogue"),
    )

    worker._run_to_review(ctrl)

    assert calls[0] == "scrape_index"
    assert worker.inventory_ready.calls == [
        ({"raw_count": 1, "valid_count": 1, "chapter_urls": ["http://example.com/ch1"]},)
    ]
    assert worker.failed.calls == []


class _FakeItem:
    def __init__(self, text: str = "") -> None:
        self._text = text

    def text(self) -> str:
        return self._text


class _FakeSignal:
    def connect(self, _callback) -> None:
        pass


class _FakeCombo:
    def __init__(self, value: str = "") -> None:
        self._value = value
        self.currentTextChanged = _FakeSignal()

    def currentText(self) -> str:
        return self._value

    def setCurrentText(self, value: str) -> None:
        self._value = value


class _FakeTable:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def rowCount(self) -> int:
        return len(self._rows)

    def item(self, row: int, column: int):
        return self._rows[row]["items"].get(column)

    def cellWidget(self, row: int, column: int):
        return self._rows[row]["widgets"].get(column)


def test_on_save_segment_speakers_updates_review_artifacts(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pipeline_page_module, "QComboBox", _FakeCombo)

    work_dir = tmp_path / "pipeline_work"
    work_dir.mkdir()

    raw_path = work_dir / "ch1_llm_raw.json"
    raw_path.write_text(
        json.dumps({"segments": [{"text": "Hello", "speaker": "narrator", "type": "narration"}]}),
        encoding="utf-8",
    )
    normalized_path = work_dir / "ch1_llm_normalized.json"
    normalized_path.write_text(
        json.dumps({"segments": [{"text": "Hello", "speaker": "narrator", "type": "narration"}]}),
        encoding="utf-8",
    )
    final_path = work_dir / "ch1_chapter_info_final.json"
    final_path.write_text(
        json.dumps({"segments": [{"text": "Hello", "speaker": "narrator", "type": "narration"}]}),
        encoding="utf-8",
    )

    page = SimpleNamespace(
        _current_review_chapter_id="ch1",
        _segment_table=_FakeTable(
            [
                {
                    "items": {0: _FakeItem("Hello")},
                    "widgets": {1: _FakeCombo("Alice"), 2: _FakeCombo("dialogue")},
                }
            ]
        ),
        _current_review_segments=[{"text": "Hello", "speaker": "narrator", "type": "narration"}],
        _current_review_row_segment_indexes=[0],
        project_manager=SimpleNamespace(get_work_dir=lambda: work_dir),
        log=_LogCapture(),
        _render_current_segments_preview=lambda: None,
        _review_stage_views={},
        _segments_to_html=lambda segments: str(segments),
    )
    page._collect_review_segments_from_table = lambda: PipelinePage._collect_review_segments_from_table(page)
    page._normalize_segment_type = PipelinePage._normalize_segment_type
    page._refresh_final_review_view = lambda chapter_id: PipelinePage._refresh_final_review_view(page, chapter_id)

    PipelinePage._on_save_segment_speakers(page)

    assert json.loads(raw_path.read_text(encoding="utf-8"))["segments"][0]["speaker"] == "Alice"
    assert json.loads(raw_path.read_text(encoding="utf-8"))["segments"][0]["type"] == "dialogue"
    assert json.loads(normalized_path.read_text(encoding="utf-8"))["segments"][0]["speaker"] == "Alice"
    assert json.loads(final_path.read_text(encoding="utf-8"))["segments"][0]["type"] == "dialogue"
    assert page.log.messages == [("Saved segment review edits for chapter review.", "SUCCESS")]


def test_on_save_detected_characters_persists_character_database(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pipeline_page_module, "QComboBox", _FakeCombo)

    work_dir = tmp_path / "pipeline_work"
    work_dir.mkdir()
    db_path = work_dir / "character_database.json"
    db_path.write_text(
        json.dumps([{"name": "Alice", "gender": "female", "voice": "af_bella", "description": "Lead"}]),
        encoding="utf-8",
    )

    settings_data = {"character_db": [], "pending_character_additions": [{"name": "Old"}]}
    settings = SimpleNamespace(
        get=lambda key, default=None: settings_data.get(key, default),
        set=lambda key, value: settings_data.__setitem__(key, value),
        save=lambda: settings_data.__setitem__("saved", True),
    )
    page = SimpleNamespace(
        _detected_char_table=_FakeTable(
            [
                {
                    "items": {
                        0: _FakeItem("Alice"),
                        3: _FakeItem("1.2"),
                        4: _FakeItem("ch1"),
                    },
                    "widgets": {1: _FakeCombo("female"), 2: _FakeCombo("af_bella")},
                },
                {
                    "items": {
                        0: _FakeItem("Bob"),
                        3: _FakeItem("0.5"),
                        4: _FakeItem("ch2"),
                    },
                    "widgets": {1: _FakeCombo("male"), 2: _FakeCombo("am_adam")},
                },
            ]
        ),
        project_manager=SimpleNamespace(get_work_dir=lambda: work_dir),
        settings=settings,
        log=_LogCapture(),
        _refresh_segment_speaker_options=lambda: None,
    )
    page._normalize_gender = PipelinePage._normalize_gender
    page._default_voice_for_gender = lambda gender: "af_heart"
    page._character_db_path = lambda: PipelinePage._character_db_path(page)
    page._load_character_database_entries = lambda: PipelinePage._load_character_database_entries(page)

    PipelinePage._on_save_detected_characters(page)

    saved = json.loads(db_path.read_text(encoding="utf-8"))
    assert saved == [
        {"name": "Alice", "gender": "female", "voice": "af_bella", "description": "Lead"},
        {"name": "Bob", "gender": "male", "voice": "am_adam", "description": ""},
    ]
    assert settings_data["character_db"] == saved
    assert settings_data["pending_character_additions"] == []
    assert settings_data["saved"] is True
    assert page.log.messages == [("Saved character edits (1 confidence values clamped to 0..1).", "WARNING")]


def test_run_continue_audio_finalizes_review_before_audio(tmp_path) -> None:
    worker = _PipelineWorker(
        project_manager=SimpleNamespace(),
        settings=SimpleNamespace(),
        mode=_PipelineWorker.CONTINUE_AUDIO,
        start_ch=2,
        end_ch=3,
    )
    worker.log_message = _SignalCapture()
    worker.finished_ok = _SignalCapture()

    calls: list[str] = []
    ctrl = SimpleNamespace(
        smart_review_dialogue=lambda: calls.append("smart_review_dialogue"),
        tts_generate=lambda: calls.append("tts_generate"),
        epub_build=lambda: calls.append("epub_build"),
    )

    worker._run_continue_audio(ctrl)

    assert calls == ["smart_review_dialogue", "tts_generate", "epub_build"]


def test_stop_pipeline_requests_worker_stop() -> None:
    stop_calls: list[str] = []
    page = SimpleNamespace(
        _worker=SimpleNamespace(request_stop=lambda: stop_calls.append("stop")),
        _is_busy=lambda: True,
        _stop_btn=SimpleNamespace(setEnabled=lambda _enabled: None),
        log=_LogCapture(),
    )

    PipelinePage._on_stop_pipeline(page)

    assert stop_calls == ["stop"]
    assert page.log.messages == [("Stop requested. Current phase will halt shortly.", "WARNING")]


def test_worker_abort_if_cancelled_emits_cancelled_signal() -> None:
    worker = _PipelineWorker(
        project_manager=SimpleNamespace(),
        settings=SimpleNamespace(),
        mode=_PipelineWorker.CHECK_INDEX,
    )
    worker.cancelled = _SignalCapture()
    worker._cancel_requested = True

    assert worker._abort_if_cancelled() is True
    assert worker.cancelled.calls == [("Pipeline cancelled by user.",)]


def test_on_recheck_dialogue_reparses_with_manual_hints() -> None:
    page = SimpleNamespace(
        _current_review_chapter_id="ch1",
        _segment_table=SimpleNamespace(rowCount=lambda: 1),
        _current_review_segments=[{"text": "Hello", "speaker": "Alice", "type": "dialogue"}],
        _review_chapter_combo=SimpleNamespace(currentIndex=lambda: 0),
        _on_save_segment_speakers=lambda: None,
        _on_review_chapter_changed=lambda _index: None,
        _require_project=lambda: True,
        log=_LogCapture(),
    )

    calls: list[str] = []
    controller = SimpleNamespace(
        pass2_classification=lambda: calls.append("pass2_classification"),
        smart_review_dialogue=lambda: calls.append("smart_review_dialogue"),
    )
    page.project_manager = SimpleNamespace(
        create_pipeline_controller=lambda: controller,
    )

    PipelinePage._on_recheck_dialogue(page)

    assert calls == ["pass2_classification", "smart_review_dialogue"]
    assert page.log.messages[0][1] == "INFO"
    assert page.log.messages[-1] == ("Dialogue recheck complete.", "SUCCESS")
