# src/ebook_app/ui/pages/settings_page.py
"""Settings page — edit and persist application settings."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ebook_app.core.settings_manager import APP_HOME_DIR
from ebook_app.models.tts_engine_cli import (
    DEFAULT_MODELS_DIR,
    download_kokoro_models,
)
from ebook_app.models.voice_catalog import KOKORO_VOICE_LIST
from ebook_app.ui.pages._base_page import BasePage

_DEFAULT_TTS_SERVICE_URL = "http://127.0.0.1:5005"

# ---------------------------------------------------------------------------
# Resolve TTS service paths from repository layout
# ---------------------------------------------------------------------------
_REPO_ROOT = APP_HOME_DIR.parent
_TTS_SERVICE_DIR = _REPO_ROOT / "tts_service"
_TTS_VENV_DIR = _TTS_SERVICE_DIR / ".venv_tts"
if sys.platform == "win32":
    _TTS_PYTHON = _TTS_VENV_DIR / "Scripts" / "python.exe"
else:
    _TTS_PYTHON = _TTS_VENV_DIR / "bin" / "python"


class _TtsServiceManager:
    """Module-level manager for the TTS server subprocess.

    Using class variables means the process outlives individual page instances
    (the settings page can be destroyed/recreated without killing the server).
    """

    _process: subprocess.Popen | None = None  # type: ignore[type-arg]

    @classmethod
    def start(cls, python_exe: Path, server_dir: Path, host: str, port: int) -> str:
        """Start the TTS uvicorn server.  Returns one of: 'started', 'already_running', 'error:<msg>'."""
        if cls.is_running():
            return "already_running"
        exe = str(python_exe)
        if not python_exe.exists():
            return f"error:TTS venv Python not found at {python_exe}"
        cmd = [exe, "-m", "uvicorn", "tts_server:app", "--host", host, "--port", str(port)]
        try:
            cls._process = subprocess.Popen(
                cmd,
                cwd=str(server_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            return "started"
        except Exception as exc:
            return f"error:{exc}"

    @classmethod
    def stop(cls) -> None:
        if cls._process is not None:
            try:
                cls._process.terminate()
            except Exception:
                pass
            cls._process = None

    @classmethod
    def is_running(cls) -> bool:
        return cls._process is not None and cls._process.poll() is None


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
        self._start_check_timer: QTimer | None = None
        super().__init__(**kwargs)

    def _build_ui(self) -> None:
        # Wrap everything in a scroll area so the page stays usable at any height
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        container = QWidget()
        inner = QVBoxLayout(container)
        inner.setContentsMargins(0, 0, 8, 0)
        inner.setSpacing(12)
        scroll.setWidget(container)
        self._layout.addWidget(scroll)

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

        inner.addWidget(general_group)

        # ── TTS Backend ────────────────────────────────────────────────
        backend_group = QGroupBox("TTS Backend")
        backend_vbox = QVBoxLayout(backend_group)
        backend_form = QFormLayout()

        self._backend_mode_label = QLabel("remote (fixed)")
        backend_form.addRow("Backend mode:", self._backend_mode_label)

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
        self._start_svc_btn = QPushButton("▶ Start Service")
        self._start_svc_btn.setToolTip(
            "Launch the TTS service using the .venv_tts virtual environment"
        )
        self._start_svc_btn.clicked.connect(self._on_start_service)
        svc_status_row.addWidget(self._start_svc_btn)
        self._stop_svc_btn = QPushButton("■ Stop Service")
        self._stop_svc_btn.setToolTip("Terminate the running TTS service process")
        self._stop_svc_btn.clicked.connect(self._on_stop_service)
        svc_status_row.addWidget(self._stop_svc_btn)
        self._check_svc_btn = QPushButton("Check Service")
        self._check_svc_btn.clicked.connect(self._on_check_service)
        svc_status_row.addWidget(self._check_svc_btn)
        backend_vbox.addLayout(svc_status_row)
        self._refresh_service_buttons()

        mode_note = QLabel(
            "<i>Remote-only</i>: GUI always calls tts_service/tts_server.py over HTTP.<br>"
            "Use Python 3.10 for GUI and run the TTS service in Python 3.14."
        )
        mode_note.setWordWrap(True)
        backend_vbox.addWidget(mode_note)

        inner.addWidget(backend_group)

        # ── Kokoro ONNX Models ─────────────────────────────────────────
        model_group = QGroupBox("Kokoro ONNX Models (for backend service)")
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

        inner.addWidget(model_group)

        # ── LLM / Translation API Connection ──────────────────────────
        llm_group = QGroupBox("LLM / Translation API Connection")
        llm_form = QFormLayout(llm_group)

        self._llm_url_input = QLineEdit(
            str(self.settings.get("llm_api_url", "http://localhost:5000/translate"))
        )
        self._llm_url_input.setPlaceholderText("http://localhost:5000/translate")
        llm_form.addRow("API URL:", self._llm_url_input)

        self._ollama_url_input = QLineEdit(
            str(self.settings.get("ollama_url", "http://127.0.0.1:11434/api/generate"))
        )
        self._ollama_url_input.setPlaceholderText("http://127.0.0.1:11434/api/generate")
        llm_form.addRow("Ollama URL:", self._ollama_url_input)

        self._ollama_model_input = QLineEdit(str(self.settings.get("ollama_model", "mistral")))
        self._ollama_model_input.setPlaceholderText("mistral")
        llm_form.addRow("Ollama model:", self._ollama_model_input)

        self._llm_key_input = QLineEdit(str(self.settings.get("llm_api_key", "")))
        self._llm_key_input.setPlaceholderText("Leave blank if no key is required")
        self._llm_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        llm_key_row = QHBoxLayout()
        llm_key_row.addWidget(self._llm_key_input)
        self._llm_key_show_btn = QPushButton("Show")
        self._llm_key_show_btn.setCheckable(True)
        self._llm_key_show_btn.toggled.connect(self._on_toggle_api_key_visibility)
        llm_key_row.addWidget(self._llm_key_show_btn)
        llm_form.addRow("API Key:", llm_key_row)

        key_note = QLabel("<i>⚠ API key is stored in plain text in your settings file.</i>")
        key_note.setWordWrap(True)
        llm_form.addRow("", key_note)

        inner.addWidget(llm_group)

        # ── Multi-speaker TTS ──────────────────────────────────────────
        ms_group = QGroupBox("Multi-speaker TTS")
        ms_form = QFormLayout(ms_group)

        self._multispeaker_check = QCheckBox("Enable multi-speaker mode")
        self._multispeaker_check.setChecked(
            bool(self.settings.get("multispeaker_enabled", False))
        )
        ms_form.addRow("", self._multispeaker_check)

        self._narrator_voice_combo = QComboBox()
        self._narrator_voice_combo.addItems(KOKORO_VOICE_LIST)
        narrator_voice = self.settings.get("narrator_voice", "af_heart")
        if narrator_voice in KOKORO_VOICE_LIST:
            self._narrator_voice_combo.setCurrentText(narrator_voice)
        ms_form.addRow("Narrator voice:", self._narrator_voice_combo)

        self._default_male_voice_combo = QComboBox()
        self._default_male_voice_combo.addItems(KOKORO_VOICE_LIST)
        default_male = self.settings.get("default_male_voice", "am_adam")
        if default_male in KOKORO_VOICE_LIST:
            self._default_male_voice_combo.setCurrentText(default_male)
        ms_form.addRow("Default male voice:", self._default_male_voice_combo)

        self._default_female_voice_combo = QComboBox()
        self._default_female_voice_combo.addItems(KOKORO_VOICE_LIST)
        default_female = self.settings.get("default_female_voice", "af_heart")
        if default_female in KOKORO_VOICE_LIST:
            self._default_female_voice_combo.setCurrentText(default_female)
        ms_form.addRow("Default female voice:", self._default_female_voice_combo)

        self._char_confidence_spin = QDoubleSpinBox()
        self._char_confidence_spin.setRange(0.0, 1.0)
        self._char_confidence_spin.setSingleStep(0.05)
        self._char_confidence_spin.setValue(
            float(self.settings.get("character_confidence_threshold", 0.8))
        )
        ms_form.addRow("New character threshold:", self._char_confidence_spin)

        inner.addWidget(ms_group)

        # ── Character Database ─────────────────────────────────────────
        char_group = QGroupBox("Character Database")
        char_vbox = QVBoxLayout(char_group)

        char_note = QLabel(
            "Assign a Kokoro voice to each named character for multi-speaker TTS."
        )
        char_note.setWordWrap(True)
        char_vbox.addWidget(char_note)

        self._char_table = QTableWidget(0, 4)
        self._char_table.setHorizontalHeaderLabels(
            ["Character Name", "Voice", "Gender", "Description"]
        )
        self._char_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._char_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._char_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._char_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._char_table.setMinimumHeight(160)
        char_vbox.addWidget(self._char_table)

        char_btn_row = QHBoxLayout()
        self._add_char_btn = QPushButton("Add Character")
        self._add_char_btn.clicked.connect(self._on_add_character)
        self._remove_char_btn = QPushButton("Remove Selected")
        self._remove_char_btn.clicked.connect(self._on_remove_character)
        char_btn_row.addWidget(self._add_char_btn)
        char_btn_row.addWidget(self._remove_char_btn)
        char_btn_row.addStretch()
        char_vbox.addLayout(char_btn_row)

        inner.addWidget(char_group)

        # Populate character table from saved settings
        self._load_character_db()

        pending_group = QGroupBox("Pending Character Detections")
        pending_vbox = QVBoxLayout(pending_group)
        pending_note = QLabel(
            "High-confidence LLM character suggestions. Accept to add to Character Database."
        )
        pending_note.setWordWrap(True)
        pending_vbox.addWidget(pending_note)

        self._pending_table = QTableWidget(0, 4)
        self._pending_table.setHorizontalHeaderLabels(["Name", "Gender", "Confidence", "Source Chapter"])
        self._pending_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._pending_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._pending_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._pending_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._pending_table.setMinimumHeight(140)
        pending_vbox.addWidget(self._pending_table)

        pending_btn_row = QHBoxLayout()
        self._accept_pending_btn = QPushButton("Accept Selected")
        self._accept_pending_btn.clicked.connect(self._on_accept_pending_character)
        self._reject_pending_btn = QPushButton("Reject Selected")
        self._reject_pending_btn.clicked.connect(self._on_reject_pending_character)
        pending_btn_row.addWidget(self._accept_pending_btn)
        pending_btn_row.addWidget(self._reject_pending_btn)
        pending_btn_row.addStretch()
        pending_vbox.addLayout(pending_btn_row)
        self._load_pending_additions()
        inner.addWidget(pending_group)

        # ── Save ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        inner.addLayout(btn_row)

        inner.addStretch()

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
            self._model_status_label.setText(
                "✅ Model files found for the remote TTS backend service."
            )
            self._model_status_label.setStyleSheet("color: green;")
        else:
            missing = []
            if not model_ok:
                missing.append("model (.onnx)")
            if not voices_ok:
                missing.append("voices (.bin)")
            msg = f"⚠ Missing: {', '.join(missing)}. Click Download to fetch them."
            self._model_status_label.setText(msg)
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

    def _on_toggle_api_key_visibility(self, checked: bool) -> None:
        if checked:
            self._llm_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self._llm_key_show_btn.setText("Hide")
        else:
            self._llm_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self._llm_key_show_btn.setText("Show")

    def _load_character_db(self) -> None:
        """Populate the character table from saved settings."""
        chars = self.settings.get("character_db", [])
        self._char_table.setRowCount(0)
        for char in chars:
            self._insert_character_row(
                char.get("name", ""),
                char.get("voice", KOKORO_VOICE_LIST[0] if KOKORO_VOICE_LIST else ""),
                char.get("gender", "unknown"),
                char.get("description", ""),
            )

    def _insert_character_row(
        self,
        name: str = "",
        voice: str = "",
        gender: str = "unknown",
        description: str = "",
    ) -> None:
        row = self._char_table.rowCount()
        self._char_table.insertRow(row)
        self._char_table.setItem(row, 0, QTableWidgetItem(name))

        voice_combo = QComboBox()
        voice_combo.addItems(KOKORO_VOICE_LIST)
        if voice in KOKORO_VOICE_LIST:
            voice_combo.setCurrentText(voice)
        self._char_table.setCellWidget(row, 1, voice_combo)

        gender_combo = QComboBox()
        gender_combo.addItems(["unknown", "male", "female"])
        if gender in {"unknown", "male", "female"}:
            gender_combo.setCurrentText(gender)
        self._char_table.setCellWidget(row, 2, gender_combo)

        self._char_table.setItem(row, 3, QTableWidgetItem(description))

    def _collect_character_db(self) -> list:
        """Read all rows from the character table and return as a list of dicts."""
        chars = []
        for row in range(self._char_table.rowCount()):
            name_item = self._char_table.item(row, 0)
            voice_widget = self._char_table.cellWidget(row, 1)
            gender_widget = self._char_table.cellWidget(row, 2)
            desc_item = self._char_table.item(row, 3)
            name = name_item.text().strip() if name_item else ""
            voice = voice_widget.currentText() if voice_widget else ""
            gender = gender_widget.currentText() if gender_widget else "unknown"
            description = desc_item.text().strip() if desc_item else ""
            if name:
                chars.append(
                    {
                        "name": name,
                        "voice": voice,
                        "gender": gender,
                        "description": description,
                    }
                )
        return chars

    def _load_pending_additions(self) -> None:
        self._pending_table.setRowCount(0)
        for item in self.settings.get("pending_character_additions", []) or []:
            self._insert_pending_row(
                name=item.get("name", ""),
                gender=item.get("gender", "unknown"),
                confidence=float(item.get("confidence", 0.0)),
                source=item.get("source_chapter", ""),
            )

    def _insert_pending_row(self, *, name: str, gender: str, confidence: float, source: str) -> None:
        row = self._pending_table.rowCount()
        self._pending_table.insertRow(row)
        self._pending_table.setItem(row, 0, QTableWidgetItem(name))
        self._pending_table.setItem(row, 1, QTableWidgetItem(gender))
        self._pending_table.setItem(row, 2, QTableWidgetItem(f"{confidence:.2f}"))
        self._pending_table.setItem(row, 3, QTableWidgetItem(source))

    def _collect_pending_additions(self) -> list:
        pending = []
        for row in range(self._pending_table.rowCount()):
            name_item = self._pending_table.item(row, 0)
            gender_item = self._pending_table.item(row, 1)
            conf_item = self._pending_table.item(row, 2)
            source_item = self._pending_table.item(row, 3)
            name = name_item.text().strip() if name_item else ""
            if not name:
                continue
            try:
                confidence = float(conf_item.text()) if conf_item else 0.0
            except (TypeError, ValueError):
                confidence = 0.0
            pending.append(
                {
                    "name": name,
                    "gender": (gender_item.text().strip() if gender_item else "unknown") or "unknown",
                    "confidence": confidence,
                    "source_chapter": source_item.text().strip() if source_item else "",
                }
            )
        return pending

    def _default_voice_for_gender(self, gender: str) -> str:
        gender_lc = (gender or "").strip().lower()
        if gender_lc == "male":
            return self._default_male_voice_combo.currentText() or "am_adam"
        if gender_lc == "female":
            return self._default_female_voice_combo.currentText() or "af_heart"
        return self._narrator_voice_combo.currentText() or "af_heart"

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        self.settings.set("output_dir", self._output_dir_input.text().strip())
        self.settings.set("tts_backend_mode", "remote")
        self.settings.set("tts_backend_url", self._backend_url_input.text().strip())
        self.settings.set("tts_autostart_service", self._autostart_check.isChecked())
        self.settings.set("kokoro_model_path", self._model_path_input.text().strip())
        self.settings.set("kokoro_voices_path", self._voices_path_input.text().strip())
        self.settings.set("llm_api_url", self._llm_url_input.text().strip())
        self.settings.set("llm_api_key", self._llm_key_input.text())
        self.settings.set("ollama_url", self._ollama_url_input.text().strip())
        self.settings.set("ollama_model", self._ollama_model_input.text().strip())
        self.settings.set("multispeaker_enabled", self._multispeaker_check.isChecked())
        self.settings.set("narrator_voice", self._narrator_voice_combo.currentText())
        self.settings.set("default_male_voice", self._default_male_voice_combo.currentText())
        self.settings.set("default_female_voice", self._default_female_voice_combo.currentText())
        self.settings.set("character_confidence_threshold", self._char_confidence_spin.value())
        self.settings.set("character_db", self._collect_character_db())
        self.settings.set("pending_character_additions", self._collect_pending_additions())
        self.settings.save()
        self._refresh_model_status()
        self.log.log("Settings saved.", level="SUCCESS")

    def _on_add_character(self) -> None:
        self._insert_character_row()

    def _on_remove_character(self) -> None:
        selected = self._char_table.selectedItems()
        if selected:
            rows = sorted({item.row() for item in selected}, reverse=True)
            for row in rows:
                self._char_table.removeRow(row)

    def _on_accept_pending_character(self) -> None:
        selected = self._pending_table.selectedItems()
        if not selected:
            return
        rows = sorted({item.row() for item in selected}, reverse=True)
        existing = {
            (self._char_table.item(row, 0).text().strip().lower())
            for row in range(self._char_table.rowCount())
            if self._char_table.item(row, 0) is not None
        }
        for row in rows:
            name_item = self._pending_table.item(row, 0)
            gender_item = self._pending_table.item(row, 1)
            if not name_item:
                continue
            name = name_item.text().strip()
            if not name:
                continue
            key = name.lower()
            if key not in existing:
                gender = gender_item.text().strip() if gender_item else "unknown"
                self._insert_character_row(
                    name=name,
                    voice=self._default_voice_for_gender(gender),
                    gender=gender,
                    description="Added from LLM suggestion",
                )
                existing.add(key)
            self._pending_table.removeRow(row)

    def _on_reject_pending_character(self) -> None:
        selected = self._pending_table.selectedItems()
        if not selected:
            return
        rows = sorted({item.row() for item in selected}, reverse=True)
        for row in rows:
            self._pending_table.removeRow(row)

    def _refresh_service_buttons(self) -> None:
        running = _TtsServiceManager.is_running()
        self._start_svc_btn.setEnabled(not running)
        self._stop_svc_btn.setEnabled(running)

    def _on_start_service(self) -> None:
        url = self._backend_url_input.text().strip() or _DEFAULT_TTS_SERVICE_URL
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 5005
        except Exception:
            host, port = "127.0.0.1", 5005

        self._svc_status_label.setText("⏳ Starting TTS service…")
        self._svc_status_label.setStyleSheet("")
        self._start_svc_btn.setEnabled(False)

        result = _TtsServiceManager.start(_TTS_PYTHON, _TTS_SERVICE_DIR, host, port)
        if result == "already_running":
            self._svc_status_label.setText("ℹ️ Service was already running.")
            self._svc_status_label.setStyleSheet("color: steelblue;")
            self._refresh_service_buttons()
        elif result.startswith("error:"):
            msg = result[6:]
            self._svc_status_label.setText(f"🔴 Could not start service: {msg}")
            self._svc_status_label.setStyleSheet("color: red;")
            self.log.log(f"TTS service start failed: {msg}", level="ERROR")
            self._refresh_service_buttons()
        else:
            self._svc_status_label.setText("⏳ Service starting — checking health in 3 s…")
            self.log.log("TTS service process launched.", level="INFO")
            self._refresh_service_buttons()
            # Auto-check health after a short delay to let the server come up
            if self._start_check_timer is not None:
                self._start_check_timer.stop()
                self._start_check_timer.deleteLater()
                self._start_check_timer = None
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._on_check_service)
            timer.start(3000)
            self._start_check_timer = timer

    def _on_stop_service(self) -> None:
        _TtsServiceManager.stop()
        self._svc_status_label.setText("⬛ Service stopped.")
        self._svc_status_label.setStyleSheet("color: gray;")
        self.log.log("TTS service process terminated.", level="INFO")
        self._refresh_service_buttons()

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
        self._refresh_service_buttons()

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
