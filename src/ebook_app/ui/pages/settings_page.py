# src/ebook_app/ui/pages/settings_page.py
"""Settings page — edit and persist application settings."""

from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
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

from ebook_app.models.voice_catalog import KOKORO_VOICE_LIST
from ebook_app.ui.pages._base_page import BasePage

_DEFAULT_TTS_SERVICE_URL = "http://127.0.0.1:5005"
_EMPTY_MODEL_LABEL = "(blank)"
_TTS_STARTUP_DELAY_MS = 1500


class _ServiceHealthThread(QThread):
    result = Signal(dict)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        from ebook_app.services.tts_client import TTSClient

        client = TTSClient(base_url=self._url)
        self.result.emit(client.health())


class _PreviewThread(QThread):
    result = Signal(dict)

    def __init__(self, url: str, voice: str, speed: float, parent=None):
        super().__init__(parent)
        self._url = url
        self._voice = voice
        self._speed = speed

    def run(self) -> None:
        from ebook_app.services.tts_client import TTSClient

        client = TTSClient(base_url=self._url)
        self.result.emit(client.preview(voice=self._voice, speed=self._speed))


class _LlmHealthThread(QThread):
    result = Signal(dict)

    def __init__(self, llm_url: str, model: str, parent=None):
        super().__init__(parent)
        self._llm_url = llm_url.strip()
        self._model = model.strip()

    @staticmethod
    def _normalize_model_name(model_name: str) -> str:
        """Normalize Ollama model names by dropping optional suffixes after the first colon."""
        return (model_name or "").split(":", 1)[0].strip()

    def run(self) -> None:
        from urllib.parse import urlparse, urlunparse
        import requests

        try:
            parsed = urlparse(self._llm_url)
            if not parsed.scheme or not parsed.netloc:
                self.result.emit(
                    {
                        "status": "unreachable",
                        "detail": "Invalid Ollama URL.",
                        "llm_url": self._llm_url,
                    }
                )
                return

            tags_url = urlunparse((parsed.scheme, parsed.netloc, "/api/tags", "", "", ""))
            response = requests.get(tags_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            models = data.get("models", []) if isinstance(data, dict) else []
            model_names: set[str] = set()
            for model in models:
                if not isinstance(model, dict):
                    continue
                normalized = self._normalize_model_name(str(model.get("name", "")))
                if normalized:
                    model_names.add(normalized)
            selected_model = self._normalize_model_name(self._model)
            model_configured = bool(selected_model)
            model_found = model_configured and (selected_model in model_names)
            self.result.emit(
                {
                    "status": "ok",
                    "detail": "",
                    "llm_url": self._llm_url,
                    "tags_url": tags_url,
                    "model": self._model,
                    "model_configured": model_configured,
                    "model_found": model_found,
                }
            )
        except (requests.RequestException, ValueError, TypeError) as exc:
            self.result.emit(
                {
                    "status": "unreachable",
                    "detail": str(exc),
                    "llm_url": self._llm_url,
                }
            )


class SettingsPage(BasePage):
    """Page for viewing and editing all persisted application settings."""

    def __init__(self, **kwargs) -> None:
        self._svc_health_thread: _ServiceHealthThread | None = None
        self._llm_health_thread: _LlmHealthThread | None = None
        self._preview_thread: _PreviewThread | None = None
        # QMediaPlayer and QAudioOutput are created lazily to avoid importing
        # QtMultimedia at module load time (optional dependency).
        self._media_player = None
        self._audio_output = None
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

        backend_vbox.addLayout(backend_form)

        # Service status row
        svc_status_row = QHBoxLayout()
        self._svc_status_label = QLabel("ℹ️ TTS server not checked yet.")
        self._svc_status_label.setStyleSheet("color: steelblue;")
        svc_status_row.addWidget(self._svc_status_label)
        svc_status_row.addStretch()
        self._start_tts_btn = QPushButton("Start TTS Server")
        self._start_tts_btn.setToolTip(
            "Launch the local TTS service using the repository TTS environment "
            "(does not check if the service is already running)"
        )
        self._start_tts_btn.clicked.connect(self._on_start_tts_server)
        svc_status_row.addWidget(self._start_tts_btn)
        self._test_tts_btn = QPushButton("Test TTS Server")
        self._test_tts_btn.setToolTip("Check that the remote TTS server is reachable and models are loaded")
        self._test_tts_btn.clicked.connect(self._on_test_tts_server)
        svc_status_row.addWidget(self._test_tts_btn)
        backend_vbox.addLayout(svc_status_row)

        mode_note = QLabel(
            "<i>Remote-only</i>: GUI always calls tts_service/tts_server.py over HTTP.<br>"
            "Use <b>Start TTS Server</b> for the default local service, or run it manually: "
            "<tt>cd tts_service &amp;&amp; python -m uvicorn tts_server:app --host 127.0.0.1 --port 5005</tt>"
        )
        mode_note.setWordWrap(True)
        backend_vbox.addWidget(mode_note)

        inner.addWidget(backend_group)

        # ── Dialogue LLM Connection ───────────────────────────────────
        llm_group = QGroupBox("Dialogue LLM Connection")
        llm_form = QFormLayout(llm_group)

        self._dialogue_llm_url_input = QLineEdit(
            str(self.settings.get("dialogue_llm_url", "http://127.0.0.1:11434/api/chat"))
        )
        self._dialogue_llm_url_input.setPlaceholderText("http://127.0.0.1:11434/api/chat")
        llm_form.addRow("Dialogue LLM URL:", self._dialogue_llm_url_input)

        self._dialogue_llm_model_input = QLineEdit(
            str(self.settings.get("dialogue_llm_model", "mistral:instruct"))
        )
        self._dialogue_llm_model_input.setPlaceholderText("mistral:instruct")
        llm_form.addRow("Dialogue LLM model:", self._dialogue_llm_model_input)

        llm_status_row = QHBoxLayout()
        self._llm_status_label = QLabel()
        self._llm_status_label.setText("ℹ️ Local LLM connection not checked yet.")
        self._llm_status_label.setStyleSheet("color: steelblue;")
        llm_status_row.addWidget(self._llm_status_label)
        llm_status_row.addStretch()
        self._check_llm_btn = QPushButton("Check Local LLM")
        self._check_llm_btn.clicked.connect(self._on_check_llm_connection)
        llm_status_row.addWidget(self._check_llm_btn)
        llm_form.addRow("", llm_status_row)

        self._llm_troubleshoot_label = QLabel()
        self._llm_troubleshoot_label.setWordWrap(True)
        self._llm_troubleshoot_label.setStyleSheet("color: orange;")
        self._llm_troubleshoot_label.hide()
        llm_form.addRow("", self._llm_troubleshoot_label)

        inner.addWidget(llm_group)

        # ── Voice Routing ──────────────────────────────────────────────
        ms_group = QGroupBox("Voice Routing")
        ms_form = QFormLayout(ms_group)

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

        self._tts_speed_spin = QDoubleSpinBox()
        self._tts_speed_spin.setRange(0.5, 2.0)
        self._tts_speed_spin.setSingleStep(0.1)
        self._tts_speed_spin.setDecimals(1)
        self._tts_speed_spin.setValue(float(self.settings.get("tts_speed", 1.0)))
        ms_form.addRow("TTS speed:", self._tts_speed_spin)

        # Preview Voice row
        preview_row = QHBoxLayout()
        self._preview_voice_combo = QComboBox()
        self._preview_voice_combo.addItems(KOKORO_VOICE_LIST)
        preview_voice = self.settings.get("narrator_voice", "af_heart")
        if preview_voice in KOKORO_VOICE_LIST:
            self._preview_voice_combo.setCurrentText(preview_voice)
        preview_row.addWidget(self._preview_voice_combo)
        self._preview_voice_btn = QPushButton("Preview Voice")
        self._preview_voice_btn.setToolTip("Send a test phrase to the TTS server and play back the audio")
        self._preview_voice_btn.clicked.connect(self._on_preview_voice)
        preview_row.addWidget(self._preview_voice_btn)
        self._preview_status_label = QLabel()
        preview_row.addWidget(self._preview_status_label)
        preview_row.addStretch()
        ms_form.addRow("Preview voice:", preview_row)

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

        self._pending_table = QTableWidget(0, 5)
        self._pending_table.setHorizontalHeaderLabels(
            ["Name", "Gender", "Voice", "Confidence", "Source Chapter"]
        )
        self._pending_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._pending_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._pending_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._pending_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._pending_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
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

    def _browse_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self._output_dir_input.setText(path)

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
                voice=item.get("voice", self._default_voice_for_gender(item.get("gender", "unknown"))),
                confidence=float(item.get("confidence", 0.0)),
                source=item.get("source_chapter", ""),
            )

    def _insert_pending_row(
        self, *, name: str, gender: str, voice: str, confidence: float, source: str
    ) -> None:
        row = self._pending_table.rowCount()
        self._pending_table.insertRow(row)
        self._pending_table.setItem(row, 0, QTableWidgetItem(name))
        self._pending_table.setItem(row, 1, QTableWidgetItem(gender))
        self._pending_table.setItem(row, 2, QTableWidgetItem(voice))
        self._pending_table.setItem(row, 3, QTableWidgetItem(f"{confidence:.2f}"))
        self._pending_table.setItem(row, 4, QTableWidgetItem(source))

    def _collect_pending_additions(self) -> list:
        pending = []
        for row in range(self._pending_table.rowCount()):
            name_item = self._pending_table.item(row, 0)
            gender_item = self._pending_table.item(row, 1)
            voice_item = self._pending_table.item(row, 2)
            conf_item = self._pending_table.item(row, 3)
            source_item = self._pending_table.item(row, 4)
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
                    "voice": (voice_item.text().strip() if voice_item else "") or self._default_voice_for_gender(
                        gender_item.text().strip() if gender_item else "unknown"
                    ),
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
        self.settings.set("tts_backend_url", self._backend_url_input.text().strip())
        dialogue_llm_url = self._dialogue_llm_url_input.text().strip()
        dialogue_llm_model = self._dialogue_llm_model_input.text().strip()
        self.settings.set("dialogue_llm_url", dialogue_llm_url)
        self.settings.set("dialogue_llm_model", dialogue_llm_model)
        self.settings.set("narrator_voice", self._narrator_voice_combo.currentText())
        self.settings.set("default_male_voice", self._default_male_voice_combo.currentText())
        self.settings.set("default_female_voice", self._default_female_voice_combo.currentText())
        self.settings.set("tts_speed", self._tts_speed_spin.value())
        self.settings.set("character_confidence_threshold", self._char_confidence_spin.value())
        self.settings.set("character_db", self._collect_character_db())
        self.settings.set("pending_character_additions", self._collect_pending_additions())
        self.settings.save()
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
            voice_item = self._pending_table.item(row, 2)
            if not name_item:
                continue
            name = name_item.text().strip()
            if not name:
                continue
            key = name.lower()
            if key not in existing:
                gender = gender_item.text().strip() if gender_item else "unknown"
                voice = (voice_item.text().strip() if voice_item else "") or self._default_voice_for_gender(gender)
                self._insert_character_row(
                    name=name,
                    voice=voice,
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

    def _on_test_tts_server(self) -> None:
        if self._svc_health_thread and self._svc_health_thread.isRunning():
            return
        if self._svc_health_thread is not None:
            try:
                self._svc_health_thread.result.disconnect(self._on_tts_test_result)
            except RuntimeError:
                pass
            self._svc_health_thread.deleteLater()
        url = self._backend_url_input.text().strip() or _DEFAULT_TTS_SERVICE_URL
        self._svc_status_label.setText("⏳ Testing TTS server…")
        self._svc_status_label.setStyleSheet("")
        self._test_tts_btn.setEnabled(False)
        self._svc_health_thread = _ServiceHealthThread(url, parent=self)
        self._svc_health_thread.result.connect(self._on_tts_test_result)
        self._svc_health_thread.start()

    def _on_start_tts_server(self) -> None:
        from ebook_app.services.tts_service_launcher import launch_tts_service

        url = self._backend_url_input.text().strip() or _DEFAULT_TTS_SERVICE_URL
        try:
            pid = launch_tts_service(url)
        except (FileNotFoundError, OSError, ValueError) as exc:
            self._svc_status_label.setText(f"🔴 Could not start TTS server: {exc}")
            self._svc_status_label.setStyleSheet("color: red;")
            self.log.log(f"Failed to start TTS server: {exc}", level="ERROR")
            return

        self._svc_status_label.setText(
            f"⏳ Started local TTS server process (PID {pid}). Checking health…"
        )
        self._svc_status_label.setStyleSheet("color: steelblue;")
        self.log.log(f"Started local TTS server process (PID {pid}).", level="INFO")
        QTimer.singleShot(_TTS_STARTUP_DELAY_MS, self._on_test_tts_server)

    def _on_tts_test_result(self, health: dict) -> None:
        self._test_tts_btn.setEnabled(True)
        status = health.get("status", "unknown")
        models_ready = health.get("models_ready", False)
        url = self._backend_url_input.text().strip() or _DEFAULT_TTS_SERVICE_URL

        if status == "unreachable":
            self._svc_status_label.setText(f"🔴 TTS server not reachable at {url}")
            self._svc_status_label.setStyleSheet("color: red;")
        elif status == "ok" and models_ready:
            self._svc_status_label.setText("✅ TTS server running — models ready.")
            self._svc_status_label.setStyleSheet("color: green;")
        elif status == "ok":
            model_path = health.get("model_path", "")
            self._svc_status_label.setText(
                f"⚠ TTS server running but models missing at {model_path}"
            )
            self._svc_status_label.setStyleSheet("color: orange;")
        else:
            self._svc_status_label.setText(
                f"⚠ TTS server error: {health.get('detail', '')}"
            )
            self._svc_status_label.setStyleSheet("color: orange;")

    def _on_check_llm_connection(self) -> None:
        if self._llm_health_thread and self._llm_health_thread.isRunning():
            return
        if self._llm_health_thread is not None:
            try:
                self._llm_health_thread.result.disconnect(self._on_llm_health_result)
            except RuntimeError:
                # Signal may already be disconnected if the prior thread was cleaned up.
                pass
            self._llm_health_thread.deleteLater()
        llm_url = self._dialogue_llm_url_input.text().strip()
        model = self._dialogue_llm_model_input.text().strip()
        self._llm_status_label.setText("⏳ Checking local LLM connection…")
        self._llm_status_label.setStyleSheet("")
        self._llm_troubleshoot_label.hide()
        self._llm_health_thread = _LlmHealthThread(llm_url, model, parent=self)
        self._llm_health_thread.result.connect(self._on_llm_health_result)
        self._llm_health_thread.start()

    def _on_llm_health_result(self, result: dict) -> None:
        if result.get("status") == "ok":
            if not result.get("model_configured", False):
                self._llm_status_label.setText(
                    "⚠ Local LLM reachable, but no model is configured in Settings."
                )
                self._llm_status_label.setStyleSheet("color: orange;")
            elif result.get("model_found", False):
                self._llm_status_label.setText("✅ Local LLM reachable and selected model is available.")
                self._llm_status_label.setStyleSheet("color: green;")
            else:
                model = result.get("model", "").strip() or _EMPTY_MODEL_LABEL
                self._llm_status_label.setText(
                    f"⚠ Local LLM reachable, but model '{model}' was not found."
                )
                self._llm_status_label.setStyleSheet("color: orange;")
            self._llm_troubleshoot_label.hide()
            return

        self._llm_status_label.setText("🔴 Could not connect to local LLM.")
        self._llm_status_label.setStyleSheet("color: red;")
        self._llm_troubleshoot_label.setText(
            self._build_llm_troubleshoot_text(
                result.get("llm_url", "").strip(),
                result.get("detail", "").strip(),
            )
        )
        self._llm_troubleshoot_label.show()

    @staticmethod
    def _build_llm_troubleshoot_text(llm_url: str, detail: str) -> str:
        target = llm_url or "the configured Dialogue LLM URL"
        detail_line = f"Details: {detail}" if detail else "Details: Connection failed."
        return (
            f"Troubleshooting for {target}:\n"
            "1) Confirm your local LLM service is running (for Ollama: `ollama serve`).\n"
            "2) Check that the URL is correct and reachable from this machine.\n"
            "3) Verify the selected model is installed (for Ollama: `ollama list`).\n"
            "4) If it still fails, check firewall/proxy settings and retry.\n"
            f"{detail_line}"
        )

    def _on_preview_voice(self) -> None:
        if self._preview_thread and self._preview_thread.isRunning():
            return
        if self._preview_thread is not None:
            try:
                self._preview_thread.result.disconnect(self._on_preview_result)
            except RuntimeError:
                pass
            self._preview_thread.deleteLater()
        url = self._backend_url_input.text().strip() or _DEFAULT_TTS_SERVICE_URL
        voice = self._preview_voice_combo.currentText()
        speed = self._tts_speed_spin.value()
        self._preview_status_label.setText("⏳ Generating…")
        self._preview_status_label.setStyleSheet("")
        self._preview_voice_btn.setEnabled(False)
        self._preview_thread = _PreviewThread(url, voice, speed, parent=self)
        self._preview_thread.result.connect(self._on_preview_result)
        self._preview_thread.start()

    def _on_preview_result(self, result: dict) -> None:
        self._preview_voice_btn.setEnabled(True)
        if "error" in result:
            self._preview_status_label.setText("🔴 Preview failed.")
            self._preview_status_label.setStyleSheet("color: red;")
            self.log.log(f"Voice preview failed: {result['error']}", level="ERROR")
            return

        audio_path = result.get("audio_path", "")
        if not audio_path:
            self._preview_status_label.setText("⚠ No audio returned.")
            self._preview_status_label.setStyleSheet("color: orange;")
            return

        self._preview_status_label.setText("🔊 Playing…")
        self._preview_status_label.setStyleSheet("color: green;")
        self._play_audio(audio_path)

    def _play_audio(self, path: str) -> None:
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            from PySide6.QtCore import QUrl

            if self._media_player is None:
                self._audio_output = QAudioOutput(self)
                self._media_player = QMediaPlayer(self)
                self._media_player.setAudioOutput(self._audio_output)

            self._media_player.stop()
            self._media_player.setSource(QUrl.fromLocalFile(path))
            self._media_player.play()
        except Exception as exc:
            self.log.log(f"Audio playback error: {exc}", level="WARNING")
