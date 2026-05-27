from __future__ import annotations

from types import SimpleNamespace

from ebook_app.ui.pages.pipeline_page import PipelinePage, QMessageBox, _PipelineWorker


class _DeletedWorker:
    def isRunning(self) -> bool:
        raise RuntimeError("libshiboken: Internal C++ object already deleted.")


class _LogCapture:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def log(self, message: str, level: str = "INFO") -> None:
        self.messages.append((message, level))


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
            "Chapter parsing is complete. Review pending character suggestions "
            "and voices in Settings, then click 'Continue Audio + Export'.",
        )
    ]
