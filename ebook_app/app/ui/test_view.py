# ebook_app/app/ui/test_view.py
"""Test / diagnostics page."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ebook_app.app.ui.base_view import BasePage

logger = logging.getLogger(__name__)


class _DiagnosticsThread(QThread):
    """Run lightweight connectivity checks in the background."""

    finished = Signal(str)

    def __init__(self, tts_url: str, llm_url: str, parent=None) -> None:
        super().__init__(parent)
        self._tts_url = tts_url
        self._llm_url = llm_url

    def run(self) -> None:
        lines: list[str] = []

        # TTS health check
        try:
            from ebook_app.tts.tts_client import TTSClient

            result = TTSClient(base_url=self._tts_url).health()
            status = result.get("status", "unknown")
            lines.append(f"[TTS]  status={status}")
        except Exception as exc:
            lines.append(f"[TTS]  ERROR: {exc}")

        # LLM connectivity check
        try:
            import requests
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(self._llm_url)
            tags_url = urlunparse(parsed._replace(path="/api/tags", query="", fragment=""))
            resp = requests.get(tags_url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            models = [m.get("name", "") for m in (data.get("models") or [])]
            lines.append(f"[LLM]  reachable  models={models[:5]}")
        except Exception as exc:
            lines.append(f"[LLM]  ERROR: {exc}")

        self.finished.emit("\n".join(lines))


class TestPage(BasePage):
    """Diagnostics and integration-test page."""

    def _build_ui(self) -> None:
        self._thread: _DiagnosticsThread | None = None

        # ── Service diagnostics ───────────────────────────────────────────
        diag_group = QGroupBox("Service Diagnostics")
        diag_layout = QVBoxLayout(diag_group)

        btn_row = QHBoxLayout()
        run_btn = QPushButton("▶ Run Diagnostics")
        run_btn.clicked.connect(self._run_diagnostics)
        btn_row.addWidget(run_btn)
        btn_row.addStretch()
        diag_layout.addLayout(btn_row)

        self._diag_output = QPlainTextEdit()
        self._diag_output.setReadOnly(True)
        self._diag_output.setMinimumHeight(120)
        self._diag_output.setPlaceholderText("Click 'Run Diagnostics' to check services…")
        diag_layout.addWidget(self._diag_output)

        self._layout.addWidget(diag_group)

        # ── Project info ──────────────────────────────────────────────────
        info_group = QGroupBox("Active Project")
        info_layout = QVBoxLayout(info_group)
        self._project_label = QLabel("(no project loaded)")
        self._project_label.setWordWrap(True)
        info_layout.addWidget(self._project_label)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self._refresh_project_info)
        info_layout.addWidget(refresh_btn)

        self._layout.addWidget(info_group)
        self._layout.addStretch()

        if self.project_manager:
            self.project_manager.project_loaded.connect(self._refresh_project_info)

        self._refresh_project_info()

    # ------------------------------------------------------------------

    def _run_diagnostics(self) -> None:
        self._diag_output.setPlainText("Running…")
        tts_url = self.settings.get("tts_backend_url", "http://127.0.0.1:5005")
        llm_url = self.settings.get("llm_url", "http://127.0.0.1:11434")
        self._thread = _DiagnosticsThread(str(tts_url), str(llm_url), self)
        self._thread.finished.connect(self._diag_output.setPlainText)
        self._thread.start()

    def _refresh_project_info(self) -> None:
        if not self.project_manager:
            self._project_label.setText("(no project manager)")
            return
        info = self.project_manager.get_project_info()
        if info:
            text = (
                f"Title:  {info.get('title', '?')}\n"
                f"Author: {info.get('author', '?')}\n"
                f"ID:     {info.get('book_id', '?')}\n"
                f"URL:    {info.get('index_url', '?')}"
            )
        else:
            text = "(no project loaded)"
        self._project_label.setText(text)
