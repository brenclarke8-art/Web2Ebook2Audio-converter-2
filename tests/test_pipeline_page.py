from __future__ import annotations

import sys
import types
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

base_page = ModuleType("ebook_app.ui.pages._base_page")
base_page.BasePage = type("BasePage", (), {})
sys.modules["ebook_app.ui.pages._base_page"] = base_page

from ebook_app.ui.pages.pipeline_page import PipelinePage, QMessageBox, _PipelineWorker


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
        set_chapter_range=lambda start, end: calls.append(f"range:{start}-{end}"),
        scrape_index=lambda: calls.append("scrape_index"),
        scrape_chapters=lambda: calls.append("scrape_chapters"),
        clean_chapters=lambda: calls.append("clean_chapters"),
        plan_clean_review=lambda: calls.append("plan_clean_review"),
        llm_semantic_analysis=lambda: calls.append("llm_semantic_analysis"),
        normalize_llm_output=lambda: calls.append("normalize_llm_output"),
        smart_review_dialogue=lambda: calls.append("smart_review_dialogue"),
    )

    worker._run_to_review(ctrl)

    assert "scrape_index" not in calls
    assert ctrl.chapter_urls == ["u1", "u2", "u3"]
    assert worker.inventory_ready.calls == [({"raw_count": 5, "valid_count": 3, "chapter_urls": ["u1", "u2", "u3"]},)]
    assert worker.failed.calls == []
    assert worker.finished_ok.calls == [
        (
            _PipelineWorker.RUN_TO_REVIEW,
            "Processing complete. Review detected characters in the Review tab before audio.",
        )
    ]
