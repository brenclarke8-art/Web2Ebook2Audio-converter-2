# ebook_app/core/startup_checker.py
"""Startup service-check dialog.

Shown as a modal dialog before the main window appears.  Runs four checks
concurrently in background threads and displays live ✅ / ❌ / ⏳ status
for each:

  1. Audio model  — kokoro-v1.0.onnx + voices-v1.0.bin present; if not,
                    download them with a progress bar.
  2. TTS service  — launch_tts_service() then poll /health (5 s timeout).
  3. Ollama       — GET /api/tags; list available models.
  4. LLM response — send a tiny test prompt; expect any valid reply.

"Proceed Anyway" is always available after all checks complete (or fail).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_ICON_PENDING = "⏳"
_ICON_OK = "✅"
_ICON_FAIL = "❌"
_ICON_SKIP = "⏭️"


# ---------------------------------------------------------------------------
# Individual check workers
# ---------------------------------------------------------------------------

class _ModelCheckWorker(QThread):
    finished = Signal(bool, str)   # (ok, message)
    progress = Signal(int)         # download progress 0-100

    def run(self) -> None:
        try:
            from ebook_app.tts.kokoro_model_setup import (
                resolve_kokoro_model_paths,
                download_and_setup_kokoro_models,
            )

            model_path, voices_path = resolve_kokoro_model_paths()
            if model_path.exists() and voices_path.exists():
                self.finished.emit(True, "Model files found.")
                return

            self.progress.emit(5)
            download_and_setup_kokoro_models()
            self.progress.emit(100)
            self.finished.emit(True, "Model files downloaded successfully.")
        except Exception as exc:
            self.finished.emit(False, f"Model setup failed: {exc}")


class _TTSServiceWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, settings: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._settings = settings

    def run(self) -> None:
        import time
        try:
            from ebook_app.tts.tts_client import TTSClient
            from ebook_app.tts.tts_service_launcher import launch_tts_service

            base_url: str = self._settings.get("tts_backend_url", "http://127.0.0.1:5005")
            client = TTSClient(base_url=base_url)

            # Try health first — maybe service is already running
            health = client.health()
            if health.get("status") == "ok":
                self.finished.emit(True, "TTS service already running.")
                return

            autostart: bool = bool(self._settings.get("tts_autostart_service", True))
            if not autostart:
                self.finished.emit(False, "TTS service not running and auto-start is disabled.")
                return

            launch_tts_service(base_url)

            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                time.sleep(0.5)
                health = client.health()
                if health.get("status") == "ok":
                    self.finished.emit(True, "TTS service started successfully.")
                    return

            self.finished.emit(False, "TTS service did not respond within 10 s.")
        except Exception as exc:
            self.finished.emit(False, f"TTS service check failed: {exc}")


class _OllamaCheckWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, settings: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._settings = settings

    def run(self) -> None:
        import requests
        from urllib.parse import urlparse

        try:
            llm_url: str = self._settings.get("llm_url", "http://127.0.0.1:11434/api/chat")
            parsed = urlparse(llm_url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            resp = requests.get(f"{base}/api/tags", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            models = [m.get("name", "") for m in (data.get("models") or [])]
            if models:
                self.finished.emit(True, f"Ollama OK — models: {', '.join(models[:5])}")
            else:
                self.finished.emit(
                    False,
                    "Ollama reachable but no models found. Pull a model with: ollama pull <name>",
                )
        except Exception as exc:
            self.finished.emit(False, f"Ollama not reachable: {exc}")


class _LLMTestWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, settings: Any, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._settings = settings

    def run(self) -> None:
        try:
            from ebook_app.text.identify.type_classifier import LLMClient

            client = LLMClient(
                base_url=self._settings.get("llm_url", ""),
                model=self._settings.get("llm_model", ""),
                timeout=10,
                retries=0,
                provider=self._settings.get("llm_provider", "ollama_local"),
                api_key=self._settings.get("llm_api_key", ""),
            )
            result = client.generate_json(
                system="Reply with valid JSON only.",
                user='{"ping": true}',
            )
            if result:
                self.finished.emit(True, f"LLM responded: {self._settings.get('llm_model', '')}")
            else:
                self.finished.emit(False, "LLM returned empty response.")
        except Exception as exc:
            self.finished.emit(False, f"LLM test failed: {exc}")


# ---------------------------------------------------------------------------
# Status row widget
# ---------------------------------------------------------------------------

class _StatusRow(QWidget):
    def __init__(self, label: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        self._icon = QLabel(_ICON_PENDING)
        self._icon.setFixedWidth(28)
        self._label = QLabel(label)
        self._label.setMinimumWidth(160)
        self._detail = QLabel("")
        self._detail.setWordWrap(True)

        layout.addWidget(self._icon)
        layout.addWidget(self._label)
        layout.addWidget(self._detail, 1)

    def set_pending(self) -> None:
        self._icon.setText(_ICON_PENDING)
        self._detail.setText("")

    def set_ok(self, detail: str = "") -> None:
        self._icon.setText(_ICON_OK)
        self._detail.setText(detail)

    def set_fail(self, detail: str = "") -> None:
        self._icon.setText(_ICON_FAIL)
        self._detail.setText(detail)
        self._detail.setStyleSheet("color: #f38ba8;")


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class StartupCheckerDialog(QDialog):
    """Modal startup-check dialog.

    Call ``exec()`` to show it.  The dialog closes automatically once all
    checks complete (or when the user clicks "Proceed Anyway").
    """

    all_checks_done = Signal()

    def __init__(self, settings: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._workers: list = []
        self._pending = 4

        self.setWindowTitle("Starting Ebook Audio Studio…")
        self.setMinimumWidth(560)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        self._build_ui()

    # ─────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("<b>Performing startup checks…</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._row_model = _StatusRow("Audio model")
        self._row_tts = _StatusRow("TTS service")
        self._row_ollama = _StatusRow("Ollama")
        self._row_llm = _StatusRow("LLM response")

        for row in (self._row_model, self._row_tts, self._row_ollama, self._row_llm):
            layout.addWidget(row)

        self._model_progress = QProgressBar()
        self._model_progress.setRange(0, 100)
        self._model_progress.setValue(0)
        self._model_progress.setVisible(False)
        layout.addWidget(self._model_progress)

        self._status_label = QLabel("Checking…")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        btn_layout = QHBoxLayout()
        self._proceed_btn = QPushButton("Proceed Anyway")
        self._proceed_btn.setEnabled(False)
        self._proceed_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(self._proceed_btn)
        layout.addLayout(btn_layout)

    # ─────────────────────────────────────────────────────────────────────
    # Check launchers
    # ─────────────────────────────────────────────────────────────────────

    def start_checks(self) -> None:
        """Launch all four checks."""
        # 1. Audio model
        w1 = _ModelCheckWorker(self)
        w1.progress.connect(self._on_model_progress)
        w1.finished.connect(self._on_model_done)
        self._workers.append(w1)

        # 2. TTS service
        w2 = _TTSServiceWorker(self._settings, self)
        w2.finished.connect(self._on_tts_done)
        self._workers.append(w2)

        # 3. Ollama
        w3 = _OllamaCheckWorker(self._settings, self)
        w3.finished.connect(self._on_ollama_done)
        self._workers.append(w3)

        # 4. LLM test
        w4 = _LLMTestWorker(self._settings, self)
        w4.finished.connect(self._on_llm_done)
        self._workers.append(w4)

        for w in self._workers:
            w.start()

    @Slot(int)
    def _on_model_progress(self, pct: int) -> None:
        self._model_progress.setVisible(True)
        self._model_progress.setValue(pct)

    @Slot(bool, str)
    def _on_model_done(self, ok: bool, msg: str) -> None:
        self._model_progress.setVisible(False)
        if ok:
            self._row_model.set_ok(msg)
        else:
            self._row_model.set_fail(msg)
        self._check_complete()

    @Slot(bool, str)
    def _on_tts_done(self, ok: bool, msg: str) -> None:
        if ok:
            self._row_tts.set_ok(msg)
        else:
            self._row_tts.set_fail(msg)
        self._check_complete()

    @Slot(bool, str)
    def _on_ollama_done(self, ok: bool, msg: str) -> None:
        if ok:
            self._row_ollama.set_ok(msg)
        else:
            self._row_ollama.set_fail(msg)
        self._check_complete()

    @Slot(bool, str)
    def _on_llm_done(self, ok: bool, msg: str) -> None:
        if ok:
            self._row_llm.set_ok(msg)
        else:
            self._row_llm.set_fail(msg)
        self._check_complete()

    def _check_complete(self) -> None:
        self._pending -= 1
        if self._pending <= 0:
            self._status_label.setText("All checks complete.")
            self._proceed_btn.setEnabled(True)
            self.all_checks_done.emit()
            # Auto-close if all checks passed
            rows = [self._row_model, self._row_tts, self._row_ollama, self._row_llm]
            if all(r._icon.text() == _ICON_OK for r in rows):
                self.accept()
