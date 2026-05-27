# src/ebook_app/ui/pages/settings_page.py
"""Settings page — edit and persist application settings."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ebook_app.models.tts_engine_cli import DEFAULT_MODELS_DIR, download_kokoro_models
from ebook_app.ui.pages._base_page import BasePage

_DEFAULT_TTS_SERVICE_URL = "http://127.0.0.1:5005"


class _DownloadThread(QThread):
    progress = Signal(str)
    finished = Signal(str, str)   # model_path, voices_path
    error = Signal(str)

    def __init__(self, dest_dir: Path, parent=None):
        super().__init__(parent)
        self.dest_dir = dest_dir

    def run(self):
        try:
            model, voices = download_kokoro_models(
                dest_dir=self.dest_dir,
                progress_callback=self.progress.emit,
            )
            self.finished.emit(str(model), str(voices))
        except Exception as exc:
            self.error.emit(str(exc))


class _ServiceHealthThread(QThread):
    result = Signal(dict)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        from ebook_app.services.tts_client import TTSClient

        client = TTSClient(base_url=self._url)
        self.result.emit(client.health())


class SettingsPage(BasePage):
    """Page for viewing and editing all persisted application settings."""

    def __init__(self, **kwargs) -> None:
        self._download_thread: _DownloadThread | None = None
        self._svc_health_thread: _ServiceHealthThread | None = None
        super().__init__(**kwargs)

    def _build_ui(self) -> None:
        # ── General ────────────────────────────────────────────────────
        general_group = QGroupBox("General")
        form = QFormLayout(general_group)

        self._output_dir_input = QLineEdit(str(self.settings.get("output_dir", "")))
        output_row = QHBoxLayout()
        output_row.addWidget(self._output_dir_input)
        browse_output = QPushButton("Browse…")
        browse_output.clicked.connect(self._browse_output_dir)
        output_row.addWidget(browse_output)
        form.addRow("Output directory:", output_row)

        self._layout.addWidget(general_group)

        # ── TTS Backend ────────────────────────────────────────────────
        backend_group = QGroupBox("TTS Backend")
        backend_vbox = QVBoxLayout(backend_group)
        backend_form = QFormLayout()

        self._backend_mode_combo = QComboBox()
        self._backend_mode_combo.addItems(["local", "remote"])
        current_mode = self.settings.get("tts_backend_mode", "local")
        self._backend_mode_combo.setCurrentText(current_mode)
        self._backend_mode_combo.currentTextChanged.connect(self._on_backend_mode_changed)
        backend_form.addRow("Backend mode:", self._backend_mode_combo)

        self._backend_url_input = QLineEdit(
            str(self.settings.get("tts_backend_url", _DEFAULT_TTS_SERVICE_URL))
        )
        self._backend_url_input.setPlaceholderText(_DEFAULT_TTS_SERVICE_URL)
        backend_form.addRow("Service URL:", self._backend_url_input)

        self._autostart_check = QCheckBox("Auto-start TTS service on launch")
        self._autostart_check.setChecked(
            bool(self.settings.get("tts_autostart_service", False))
        )
        backend_form.addRow("", self._autostart_check)

        backend_vbox.addLayout(backend_form)

        # Service status row
        svc_status_row = QHBoxLayout()
        self._svc_status_label = QLabel()
        svc_status_row.addWidget(self._svc_status_label)
        svc_status_row.addStretch()
        self._check_svc_btn = QPushButton("Check Service")
        self._check_svc_btn.clicked.connect(self._on_check_service)
        svc_status_row.addWidget(self._check_svc_btn)
        backend_vbox.addLayout(svc_status_row)

        mode_note = QLabel(
            "<i>local</i>: imports kokoro-onnx directly (requires Python env with kokoro-onnx)<br>"
            "<i>remote</i>: calls tts_service/tts_server.py over HTTP (allows separate Python env)"
        )
        mode_note.setWordWrap(True)
        backend_vbox.addWidget(mode_note)

        self._layout.addWidget(backend_group)
        self._on_backend_mode_changed(current_mode)  # set initial enabled state

        # ── Kokoro ONNX Models ─────────────────────────────────────────
        model_group = QGroupBox("Kokoro ONNX Models (local mode)")
        model_vbox = QVBoxLayout(model_group)

        model_form = QFormLayout()

        self._model_path_input = QLineEdit(str(self.settings.get("kokoro_model_path", "")))
        self._model_path_input.setPlaceholderText(
            f"Leave blank to use default: {DEFAULT_MODELS_DIR / 'kokoro-v1.0.onnx'}"
        )
        model_row = QHBoxLayout()
        model_row.addWidget(self._model_path_input)
        browse_model = QPushButton("Browse…")
        browse_model.clicked.connect(self._browse_model_path)
        model_row.addWidget(browse_model)
        model_form.addRow("Model file (.onnx):", model_row)

        self._voices_path_input = QLineEdit(str(self.settings.get("kokoro_voices_path", "")))
        self._voices_path_input.setPlaceholderText(
            f"Leave blank to use default: {DEFAULT_MODELS_DIR / 'voices-v1.0.bin'}"
        )
        voices_row = QHBoxLayout()
        voices_row.addWidget(self._voices_path_input)
        browse_voices = QPushButton("Browse…")
        browse_voices.clicked.connect(self._browse_voices_path)
        voices_row.addWidget(browse_voices)
        model_form.addRow("Voices file (.bin):", voices_row)

        model_vbox.addLayout(model_form)

        # Status label + download button
        status_row = QHBoxLayout()
        self._model_status_label = QLabel()
        self._refresh_model_status()
        status_row.addWidget(self._model_status_label)
        status_row.addStretch()

        self._download_btn = QPushButton("Download Models from GitHub")
        self._download_btn.clicked.connect(self._on_download_models)
        status_row.addWidget(self._download_btn)
        model_vbox.addLayout(status_row)

        self._layout.addWidget(model_group)

        # ── Save ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        self._layout.addLayout(btn_row)

        self._layout.addStretch()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _on_backend_mode_changed(self, mode: str) -> None:
        is_remote = mode == "remote"
        self._backend_url_input.setEnabled(is_remote)
        self._check_svc_btn.setEnabled(is_remote)
        if not is_remote:
            self._svc_status_label.setText("")

    def _refresh_model_status(self) -> None:
        from ebook_app.models.tts_engine_cli import _resolve_model_paths
        model_path, voices_path = _resolve_model_paths(
            self._model_path_input.text().strip() or None,
            self._voices_path_input.text().strip() or None,
        )
        model_ok = model_path.exists()
        voices_ok = voices_path.exists()
        if model_ok and voices_ok:
            self._model_status_label.setText("✅ Model files found — ready to use.")
            self._model_status_label.setStyleSheet("color: green;")
        else:
            missing = []
            if not model_ok:
                missing.append("model (.onnx)")
            if not voices_ok:
                missing.append("voices (.bin)")
            self._model_status_label.setText(
                f"⚠ Missing: {', '.join(missing)}. Click Download to fetch them."
            )
            self._model_status_label.setStyleSheet("color: orange;")

    def _browse_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self._output_dir_input.setText(path)

    def _browse_model_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Kokoro ONNX Model File", "", "ONNX files (*.onnx)"
        )
        if path:
            self._model_path_input.setText(path)
            self._refresh_model_status()

    def _browse_voices_path(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Kokoro Voices File", "", "Binary files (*.bin)"
        )
        if path:
            self._voices_path_input.setText(path)
            self._refresh_model_status()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        self.settings.set("output_dir", self._output_dir_input.text().strip())
        self.settings.set("tts_backend_mode", self._backend_mode_combo.currentText())
        self.settings.set("tts_backend_url", self._backend_url_input.text().strip())
        self.settings.set("tts_autostart_service", self._autostart_check.isChecked())
        self.settings.set("kokoro_model_path", self._model_path_input.text().strip())
        self.settings.set("kokoro_voices_path", self._voices_path_input.text().strip())
        self.settings.save()
        self._refresh_model_status()
        self.log.log("Settings saved.", level="SUCCESS")

    def _on_check_service(self) -> None:
        if self._svc_health_thread and self._svc_health_thread.isRunning():
            return
        # Discard old thread before creating a new one to avoid signal leaks.
        if self._svc_health_thread is not None:
            try:
                self._svc_health_thread.result.disconnect(self._on_service_health_result)
            except RuntimeError:
                pass
            self._svc_health_thread.deleteLater()
        url = self._backend_url_input.text().strip() or _DEFAULT_TTS_SERVICE_URL
        self._svc_status_label.setText("⏳ Checking…")
        self._svc_status_label.setStyleSheet("")
        self._svc_health_thread = _ServiceHealthThread(url, parent=self)
        self._svc_health_thread.result.connect(self._on_service_health_result)
        self._svc_health_thread.start()

    def _on_service_health_result(self, health: dict) -> None:
        status = health.get("status", "unknown")
        models_ready = health.get("models_ready", False)
        url = self._backend_url_input.text().strip() or _DEFAULT_TTS_SERVICE_URL

        if status == "unreachable":
            self._svc_status_label.setText(f"🔴 Service not reachable at {url}")
            self._svc_status_label.setStyleSheet("color: red;")
        elif status == "ok" and models_ready:
            self._svc_status_label.setText("✅ Service running — models ready.")
            self._svc_status_label.setStyleSheet("color: green;")
        elif status == "ok":
            model_path = health.get("model_path", "")
            self._svc_status_label.setText(
                f"⚠ Service running but models missing at {model_path}"
            )
            self._svc_status_label.setStyleSheet("color: orange;")
        else:
            self._svc_status_label.setText(
                f"⚠ Service error: {health.get('detail', '')}"
            )
            self._svc_status_label.setStyleSheet("color: orange;")

    def _on_download_models(self) -> None:
        if self._download_thread and self._download_thread.isRunning():
            return

        self._download_btn.setEnabled(False)
        self._model_status_label.setText("⏳ Downloading models…")
        self._model_status_label.setStyleSheet("")

        dest = DEFAULT_MODELS_DIR
        self._download_thread = _DownloadThread(dest, parent=self)
        self._download_thread.progress.connect(
            lambda msg: self._model_status_label.setText(f"⏳ {msg}")
        )
        self._download_thread.finished.connect(self._on_download_finished)
        self._download_thread.error.connect(self._on_download_error)
        self._download_thread.start()

    def _on_download_finished(self, model_path: str, voices_path: str) -> None:
        self._download_btn.setEnabled(True)
        # If the user hasn't specified custom paths, leave the fields blank so
        # the engine auto-discovers files in the default directory.
        self._refresh_model_status()
        self.log.log(
            f"Kokoro models downloaded to {DEFAULT_MODELS_DIR}", level="SUCCESS"
        )

    def _on_download_error(self, error: str) -> None:
        self._download_btn.setEnabled(True)
        self._refresh_model_status()
        self.log.log(f"Model download failed: {error}", level="ERROR")

