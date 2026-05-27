# src/ebook_app/ui/pages/settings_page.py
"""Settings page — edit and persist application settings."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
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


class SettingsPage(BasePage):
    """Page for viewing and editing all persisted application settings."""

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

        # ── Kokoro ONNX Models ─────────────────────────────────────────
        model_group = QGroupBox("Kokoro ONNX Models")
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

        self._download_thread: _DownloadThread | None = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
        self.settings.set("kokoro_model_path", self._model_path_input.text().strip())
        self.settings.set("kokoro_voices_path", self._voices_path_input.text().strip())
        self.settings.save()
        self._refresh_model_status()
        self.log.log("Settings saved.", level="SUCCESS")

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
