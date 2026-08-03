# ebook_app/core/startup_checker.py
"""Startup service-check dialog.

Shown as a modal dialog before the main window appears.  Runs four checks
concurrently in background threads and displays live ✅ / ❌ / ⏳ status
for each:

  1. Audio model  — kokoro-v1.0.onnx + voices-v1.0.bin present; if not,
                    offer a Download button.
  2. TTS service  — launch_tts_service() then poll /health; offer a
                    "Start Service" button if auto-start is disabled.
  3. Ollama       — GET /api/tags; populate a model selector dropdown.
  4. LLM response — send a tiny test prompt; expect any valid reply.

"Proceed Anyway" is always available after all checks complete (or fail).
The user can select or type the Ollama model directly from this dialog.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QThread, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
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

    def __init__(self, force_download: bool = False, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._force_download = force_download

    def run(self) -> None:
        try:
            from ebook_app.tts.kokoro_model_setup import (
                resolve_kokoro_model_paths,
                download_and_setup_kokoro_models,
            )

            model_path, voices_path = resolve_kokoro_model_paths()
            if not self._force_download and model_path.exists() and voices_path.exists():
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

    def __init__(self, settings: Any, force_start: bool = False,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._force_start = force_start

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

            autostart: bool = self._force_start or bool(
                self._settings.get("tts_autostart_service", True)
            )
            if not autostart:
                self.finished.emit(False, "TTS service not running (auto-start disabled).")
                return

            launch_tts_service(base_url)

            deadline = time.monotonic() + 15.0
            while time.monotonic() < deadline:
                time.sleep(0.5)
                health = client.health()
                if health.get("status") == "ok":
                    self.finished.emit(True, "TTS service started successfully.")
                    return

            self.finished.emit(False, "TTS service did not respond within 15 s.")
        except Exception as exc:
            self.finished.emit(False, f"TTS service check failed: {exc}")


class _OllamaCheckWorker(QThread):
    # (ok, message, models_list)
    finished = Signal(bool, str, list)

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
            models: List[str] = [m.get("name", "") for m in (data.get("models") or []) if m.get("name")]
            if models:
                self.finished.emit(True, f"Ollama OK — {len(models)} model(s) available.", models)
            else:
                self.finished.emit(
                    False,
                    "Ollama reachable but no models found. Pull a model with: ollama pull <name>",
                    [],
                )
        except Exception as exc:
            self.finished.emit(False, f"Ollama not reachable: {exc}", [])


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
# Status row widget (with optional action button)
# ---------------------------------------------------------------------------

class _StatusRow(QWidget):
    def __init__(self, label: str, action_label: str = "",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        self._icon = QLabel(_ICON_PENDING)
        self._icon.setFixedWidth(28)
        self._name_label = QLabel(label)
        self._name_label.setMinimumWidth(140)
        self._detail = QLabel("")
        self._detail.setWordWrap(True)

        self._action_btn = QPushButton(action_label)
        self._action_btn.setFixedWidth(100)
        self._action_btn.setVisible(False)

        layout.addWidget(self._icon)
        layout.addWidget(self._name_label)
        layout.addWidget(self._detail, 1)
        layout.addWidget(self._action_btn)

    def action_button(self) -> QPushButton:
        return self._action_btn

    def icon_text(self) -> str:
        return self._icon.text()

    def set_pending(self) -> None:
        self._icon.setText(_ICON_PENDING)
        self._detail.setText("")
        self._detail.setStyleSheet("")
        self._action_btn.setVisible(False)
        self._action_btn.setEnabled(True)

    def set_ok(self, detail: str = "") -> None:
        self._icon.setText(_ICON_OK)
        self._detail.setText(detail)
        self._detail.setStyleSheet("")
        self._action_btn.setVisible(False)

    def set_fail(self, detail: str = "", show_action: bool = False) -> None:
        self._icon.setText(_ICON_FAIL)
        self._detail.setText(detail)
        self._detail.setStyleSheet("color: #f38ba8;")
        self._action_btn.setVisible(show_action)


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class StartupCheckerDialog(QDialog):
    """Modal startup-check dialog.

    Checks start automatically when the dialog is shown.  Once all four
    checks have completed the user must click "Continue" (all passed) or
    "Proceed Anyway" (some failed) to confirm the LLM model selection and
    open the main window.
    """

    all_checks_done = Signal()

    def __init__(self, settings: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._workers: list = []
        self._started = False

        # Per-check result tracking: None = not yet done
        self._results: Dict[str, Optional[bool]] = {
            "model": None,
            "tts": None,
            "ollama": None,
            "llm": None,
        }

        self.setWindowTitle("Starting Web2Ebook2Audio Converter…")
        self.setMinimumWidth(620)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        self._build_ui()

    # ─────────────────────────────────────────────────────────────────────
    # Auto-start checks when the dialog is shown
    # ─────────────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Use singleShot so the event loop is running before threads emit signals.
        # start_checks() is idempotent — safe to call multiple times.
        QTimer.singleShot(0, self.start_checks)

    # ─────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("<b>Performing startup checks…</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # ── Check rows ────────────────────────────────────────────────────
        self._row_model = _StatusRow("Audio model", "Download")
        self._row_model.action_button().clicked.connect(self._on_download_model)

        self._row_tts = _StatusRow("TTS service", "Start Service")
        self._row_tts.action_button().clicked.connect(self._on_start_tts)

        self._row_ollama = _StatusRow("Ollama")
        self._row_llm = _StatusRow("LLM response")

        for row in (self._row_model, self._row_tts, self._row_ollama, self._row_llm):
            layout.addWidget(row)

        # ── Model download progress bar ───────────────────────────────────
        self._model_progress = QProgressBar()
        self._model_progress.setRange(0, 100)
        self._model_progress.setValue(0)
        self._model_progress.setVisible(False)
        layout.addWidget(self._model_progress)

        # ── Ollama model selector ─────────────────────────────────────────
        model_group = QGroupBox("LLM Model Selection")
        model_form = QFormLayout(model_group)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.setMinimumWidth(280)
        self._model_combo.setPlaceholderText("Detected models will appear here…")
        current_model = self._settings.get("llm_model", "")
        if current_model:
            self._model_combo.addItem(current_model)
            self._model_combo.setCurrentText(current_model)

        hint = QLabel(
            "Select a detected model or type a model name. "
            "This will be saved as your active LLM model."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 11px;")

        model_form.addRow("Model:", self._model_combo)
        model_form.addRow("", hint)
        layout.addWidget(model_group)

        # ── Status label ──────────────────────────────────────────────────
        self._status_label = QLabel("Checking…")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        self._proceed_btn = QPushButton("Proceed Anyway")
        self._proceed_btn.setEnabled(False)
        self._proceed_btn.clicked.connect(self._on_proceed)
        btn_layout.addStretch()
        btn_layout.addWidget(self._proceed_btn)
        layout.addLayout(btn_layout)

    # ─────────────────────────────────────────────────────────────────────
    # Check launchers
    # ─────────────────────────────────────────────────────────────────────

    def start_checks(self) -> None:
        """Launch all four checks concurrently in background threads."""
        if self._started:
            return
        self._started = True

        # 1. Audio model
        w1 = _ModelCheckWorker(parent=self)
        w1.progress.connect(self._on_model_progress)
        w1.finished.connect(self._on_model_done)
        self._workers.append(w1)

        # 2. TTS service
        w2 = _TTSServiceWorker(self._settings, parent=self)
        w2.finished.connect(self._on_tts_done)
        self._workers.append(w2)

        # 3. Ollama
        w3 = _OllamaCheckWorker(self._settings, parent=self)
        w3.finished.connect(self._on_ollama_done)
        self._workers.append(w3)

        # 4. LLM test
        w4 = _LLMTestWorker(self._settings, parent=self)
        w4.finished.connect(self._on_llm_done)
        self._workers.append(w4)

        for w in self._workers:
            w.start()

    # ─────────────────────────────────────────────────────────────────────
    # Retry / action handlers
    # ─────────────────────────────────────────────────────────────────────

    def _on_download_model(self) -> None:
        """User clicked 'Download' — force-download the audio model."""
        self._results["model"] = None
        self._row_model.set_pending()
        self._model_progress.setValue(0)
        self._model_progress.setVisible(True)
        self._proceed_btn.setEnabled(False)
        self._status_label.setText("Downloading audio model…")

        w = _ModelCheckWorker(force_download=True, parent=self)
        w.progress.connect(self._on_model_progress)
        w.finished.connect(self._on_model_done)
        self._workers.append(w)
        w.start()

    def _on_start_tts(self) -> None:
        """User clicked 'Start Service' — force-launch the TTS service."""
        self._results["tts"] = None
        self._row_tts.set_pending()
        self._proceed_btn.setEnabled(False)
        self._status_label.setText("Starting TTS service…")

        w = _TTSServiceWorker(self._settings, force_start=True, parent=self)
        w.finished.connect(self._on_tts_done)
        self._workers.append(w)
        w.start()

    # ─────────────────────────────────────────────────────────────────────
    # Signal handlers
    # ─────────────────────────────────────────────────────────────────────

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
            self._row_model.set_fail(msg, show_action=True)
        self._mark_done("model", ok)

    @Slot(bool, str)
    def _on_tts_done(self, ok: bool, msg: str) -> None:
        if ok:
            self._row_tts.set_ok(msg)
        else:
            self._row_tts.set_fail(msg, show_action=True)
        self._mark_done("tts", ok)

    @Slot(bool, str, list)
    def _on_ollama_done(self, ok: bool, msg: str, models: list) -> None:
        if ok:
            self._row_ollama.set_ok(msg)
        else:
            self._row_ollama.set_fail(msg)
        self._populate_model_combo(models)
        self._mark_done("ollama", ok)

    @Slot(bool, str)
    def _on_llm_done(self, ok: bool, msg: str) -> None:
        if ok:
            self._row_llm.set_ok(msg)
        else:
            self._row_llm.set_fail(msg)
        self._mark_done("llm", ok)

    # ─────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────

    def _populate_model_combo(self, models: list) -> None:
        """Populate the model combo with detected Ollama models."""
        if not models:
            return
        current = self._model_combo.currentText().strip()
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItems(models)
        # Restore user's previous selection if it's in the list, else pick first
        if current and current in models:
            self._model_combo.setCurrentText(current)
        elif current:
            # Keep the user-typed value even if not in detected list
            self._model_combo.setCurrentText(current)
        else:
            self._model_combo.setCurrentIndex(0)
        self._model_combo.blockSignals(False)

    def _mark_done(self, key: str, ok: bool) -> None:
        """Record a check result and update dialog state."""
        self._results[key] = ok
        all_done = all(v is not None for v in self._results.values())
        if all_done:
            all_ok = all(self._results.values())
            if all_ok:
                self._status_label.setText(
                    "All checks passed! Select your LLM model and click Continue."
                )
                self._proceed_btn.setText("Continue")
            else:
                self._status_label.setText("Some checks failed — see above.")
                self._proceed_btn.setText("Proceed Anyway")
            self._proceed_btn.setEnabled(True)
            self.all_checks_done.emit()

    def _on_proceed(self) -> None:
        """Save selected model and close the dialog."""
        model = self._model_combo.currentText().strip()
        if model:
            self._settings.set("llm_model", model)
        self.accept()
