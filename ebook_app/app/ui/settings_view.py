# ebook_app/app/ui/settings_view.py
"""Settings page — edit and persist application settings."""

from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ebook_app.tts.voice_catalog import KOKORO_VOICE_LIST
from ebook_app.app.ui.base_view import BasePage

_DEFAULT_TTS_SERVICE_URL = "http://127.0.0.1:5005"
_EMPTY_MODEL_LABEL = "(blank)"
_TTS_STARTUP_DELAY_MS = 1500


class _ServiceHealthThread(QThread):
    result = Signal(dict)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        from ebook_app.tts.tts_client import TTSClient

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
        from ebook_app.tts.tts_client import TTSClient

        client = TTSClient(base_url=self._url)
        self.result.emit(client.preview(voice=self._voice, speed=self._speed))


class _LlmHealthThread(QThread):
    result = Signal(dict)

    def __init__(self, provider: str, llm_url: str, model: str, api_key: str = "", parent=None):
        super().__init__(parent)
        self._provider = provider.strip()
        self._llm_url = llm_url.strip()
        self._model = model.strip()
        self._api_key = api_key.strip()

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
                        "detail": "Invalid LLM URL.",
                        "llm_url": self._llm_url,
                    }
                )
                return

            provider = self._provider.lower()
            if provider == "external_cloud":
                self.result.emit(
                    {
                        "status": "ok",
                        "detail": "",
                        "llm_url": self._llm_url,
                        "model": self._model,
                        "model_configured": bool(self._model),
                        "model_found": bool(self._model),
                        "available_models": [self._model] if self._model else [],
                        "provider": provider,
                        "api_key_configured": bool(self._api_key),
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
                    "available_models": sorted(model_names),
                    "provider": provider,
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


class _KokoroModelSetupThread(QThread):
    result = Signal(dict)

    def run(self) -> None:
        from ebook_app.tts.kokoro_model_setup import download_and_setup_kokoro_models

        try:
            paths = download_and_setup_kokoro_models()
            self.result.emit(
                {
                    "status": "ok",
                    "detail": "",
                    "model_path": paths["model_path"],
                    "voices_path": paths["voices_path"],
                }
            )
        except RuntimeError as exc:
            self.result.emit(
                {
                    "status": "error",
                    "detail": str(exc),
                }
            )


class SettingsPage(BasePage):
    """Page for viewing and editing all persisted application settings."""

    def __init__(self, **kwargs) -> None:
        self._svc_health_thread: _ServiceHealthThread | None = None
        self._llm_health_thread: _LlmHealthThread | None = None
        self._preview_thread: _PreviewThread | None = None
        self._kokoro_setup_thread: _KokoroModelSetupThread | None = None
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

        # Kokoro model file (.onnx) — optional override, auto-discovered when blank
        model_path_row = QHBoxLayout()
        self._kokoro_model_path_input = QLineEdit(
            str(self.settings.get("kokoro_model_path", ""))
        )
        self._kokoro_model_path_input.setPlaceholderText(
            "auto (<repo>/.ebook_audio_studio/models/kokoro-v1.0.onnx)"
        )
        model_path_row.addWidget(self._kokoro_model_path_input)
        browse_model = QPushButton("Browse…")
        browse_model.clicked.connect(self._browse_kokoro_model)
        model_path_row.addWidget(browse_model)
        backend_form.addRow("Model file (.onnx):", model_path_row)

        # Kokoro voices file (.bin) — optional override, auto-discovered when blank
        voices_path_row = QHBoxLayout()
        self._kokoro_voices_path_input = QLineEdit(
            str(self.settings.get("kokoro_voices_path", ""))
        )
        self._kokoro_voices_path_input.setPlaceholderText(
            "auto (<repo>/.ebook_audio_studio/models/voices-v1.0.bin)"
        )
        voices_path_row.addWidget(self._kokoro_voices_path_input)
        browse_voices = QPushButton("Browse…")
        browse_voices.clicked.connect(self._browse_kokoro_voices)
        voices_path_row.addWidget(browse_voices)
        backend_form.addRow("Voices file (.bin):", voices_path_row)

        backend_vbox.addLayout(backend_form)

        # Service status row
        svc_status_row = QHBoxLayout()
        self._svc_status_label = QLabel("ℹ️ TTS server not checked yet.")
        self._svc_status_label.setStyleSheet("color: steelblue;")
        svc_status_row.addWidget(self._svc_status_label)
        svc_status_row.addStretch()
        self._start_tts_btn = QPushButton("Start TTS Server")
        self._start_tts_btn.setToolTip("Launch the local TTS service using the repository TTS environment.")
        self._start_tts_btn.clicked.connect(self._on_start_tts_server)
        svc_status_row.addWidget(self._start_tts_btn)
        self._setup_kokoro_btn = QPushButton("Download + Setup Kokoro Models")
        self._setup_kokoro_btn.setToolTip(
            "Download kokoro-v1.0.onnx and voices-v1.0.bin into the default models folder. "
            "Safe to run again to repair or refresh existing files."
        )
        self._setup_kokoro_btn.clicked.connect(self._on_setup_kokoro_models)
        svc_status_row.addWidget(self._setup_kokoro_btn)
        self._test_tts_btn = QPushButton("Test TTS Server")
        self._test_tts_btn.setToolTip("Check that the remote TTS server is reachable and models are loaded")
        self._test_tts_btn.clicked.connect(self._on_test_tts_server)
        svc_status_row.addWidget(self._test_tts_btn)
        backend_vbox.addLayout(svc_status_row)

        mode_note = QLabel(
            "<i>Remote-only</i>: GUI always calls tts_service/tts_server.py over HTTP.<br>"
            "Use <b>Download + Setup Kokoro Models</b> once, then <b>Start TTS Server</b> for the default local "
            "service (safe to re-run if files need repair). Alternatively, run it manually for the default local URL: "
            "<tt>cd tts_service &amp;&amp; python -m uvicorn tts_server:app --host 127.0.0.1 --port 5005</tt>"
        )
        mode_note.setWordWrap(True)
        backend_vbox.addWidget(mode_note)

        inner.addWidget(backend_group)

        # ── Dialogue LLM Connection ───────────────────────────────────
        llm_group = QGroupBox("Dialogue LLM Connection")
        llm_form = QFormLayout(llm_group)

        self._llm_provider_combo = QComboBox()
        self._llm_provider_combo.addItem("Local Ollama", userData="ollama_local")
        self._llm_provider_combo.addItem("External Cloud API", userData="external_cloud")
        provider = str(self.settings.get("llm_provider", "ollama_local"))
        provider_idx = self._llm_provider_combo.findData(provider)
        self._llm_provider_combo.setCurrentIndex(provider_idx if provider_idx >= 0 else 0)
        llm_form.addRow("LLM provider:", self._llm_provider_combo)

        self._dialogue_llm_url_input = QLineEdit(
            str(self.settings.get("llm_url", self.settings.get("dialogue_llm_url", "http://127.0.0.1:11434/api/generate")))
        )
        self._dialogue_llm_url_input.setPlaceholderText("http://127.0.0.1:11434/api/generate")
        llm_form.addRow("LLM URL:", self._dialogue_llm_url_input)

        self._llm_api_key_input = QLineEdit(str(self.settings.get("llm_api_key", "")))
        self._llm_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._llm_api_key_input.setPlaceholderText("Optional for local Ollama")
        llm_form.addRow("API key:", self._llm_api_key_input)

        self._dialogue_llm_model_input = QComboBox()
        self._dialogue_llm_model_input.setEditable(True)
        configured_model = str(self.settings.get("llm_model", self.settings.get("dialogue_llm_model", "qwen2.5-coder:7b")))
        if configured_model:
            self._dialogue_llm_model_input.addItem(configured_model)
        self._dialogue_llm_model_input.setCurrentText(configured_model)
        llm_form.addRow("LLM model:", self._dialogue_llm_model_input)

        llm_status_row = QHBoxLayout()
        self._llm_status_label = QLabel()
        self._llm_status_label.setText("ℹ️ LLM connection not checked yet.")
        self._llm_status_label.setStyleSheet("color: steelblue;")
        llm_status_row.addWidget(self._llm_status_label)
        llm_status_row.addStretch()
        self._refresh_llm_models_btn = QPushButton("Refresh Models")
        self._refresh_llm_models_btn.clicked.connect(self._on_check_llm_connection)
        llm_status_row.addWidget(self._refresh_llm_models_btn)
        self._check_llm_btn = QPushButton("Check LLM")
        self._check_llm_btn.clicked.connect(self._on_check_llm_connection)
        llm_status_row.addWidget(self._check_llm_btn)
        llm_form.addRow("", llm_status_row)

        self._llm_troubleshoot_label = QLabel()
        self._llm_troubleshoot_label.setWordWrap(True)
        self._llm_troubleshoot_label.setStyleSheet("color: orange;")
        self._llm_troubleshoot_label.hide()
        llm_form.addRow("", self._llm_troubleshoot_label)

        inner.addWidget(llm_group)
        self._llm_provider_combo.currentIndexChanged.connect(self._on_llm_provider_changed)
        self._on_llm_provider_changed()

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
        default_female = self.settings.get("default_female_voice", "af_bella")
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

        # ── Scraper ────────────────────────────────────────────────────
        scraper_group = QGroupBox("Scraper")
        scraper_form = QFormLayout(scraper_group)

        self._scraper_method_combo = QComboBox()
        self._scraper_method_combo.addItems(["browser", "http"])
        self._scraper_method_combo.setCurrentText(
            str(self.settings.get("scraper_method", "browser"))
        )
        self._scraper_method_combo.setToolTip(
            "browser — use a headless Chromium/Firefox via Playwright (handles JS-heavy sites).\n"
            "http — plain HTTP requests via requests library (faster, no JS support)."
        )
        scraper_form.addRow("Scraper method:", self._scraper_method_combo)

        self._scraper_use_gui_cb = QCheckBox("Show browser window (disable headless)")
        self._scraper_use_gui_cb.setChecked(
            bool(self.settings.get("scraper_use_browser_gui", False))
        )
        scraper_form.addRow("", self._scraper_use_gui_cb)

        self._scraper_manual_nav_cb = QCheckBox("Enable manual navigation mode")
        self._scraper_manual_nav_cb.setToolTip(
            "When enabled, the browser window opens and waits for you to navigate "
            "manually (e.g. to log in) before continuing the scrape."
        )
        self._scraper_manual_nav_cb.setChecked(
            bool(self.settings.get("scraper_manual_navigation", False))
        )
        scraper_form.addRow("", self._scraper_manual_nav_cb)

        self._scraper_manual_nav_timeout_spin = QSpinBox()
        self._scraper_manual_nav_timeout_spin.setRange(10, 3600)
        self._scraper_manual_nav_timeout_spin.setSuffix(" s")
        self._scraper_manual_nav_timeout_spin.setValue(
            int(self.settings.get("scraper_manual_navigation_timeout_sec", 120))
        )
        scraper_form.addRow("Manual nav timeout:", self._scraper_manual_nav_timeout_spin)

        self._scraper_max_index_pages_spin = QSpinBox()
        self._scraper_max_index_pages_spin.setRange(1, 9999)
        self._scraper_max_index_pages_spin.setValue(
            int(self.settings.get("scraper_max_index_pages", 50))
        )
        self._scraper_max_index_pages_spin.setToolTip(
            "Maximum number of index/listing pages to follow when building the chapter list."
        )
        scraper_form.addRow("Max index pages:", self._scraper_max_index_pages_spin)

        self._scraper_browser_timeout_spin = QSpinBox()
        self._scraper_browser_timeout_spin.setRange(5, 300)
        self._scraper_browser_timeout_spin.setSuffix(" s")
        self._scraper_browser_timeout_spin.setValue(
            int(self.settings.get("scraper_browser_timeout_sec", 30))
        )
        scraper_form.addRow("Browser page timeout:", self._scraper_browser_timeout_spin)

        self._scraper_delay_spin = QSpinBox()
        self._scraper_delay_spin.setRange(0, 30000)
        self._scraper_delay_spin.setSuffix(" ms")
        self._scraper_delay_spin.setValue(
            int(self.settings.get("scraper_delay_ms", 500))
        )
        self._scraper_delay_spin.setToolTip(
            "Polite delay between consecutive chapter requests (milliseconds)."
        )
        scraper_form.addRow("Request delay:", self._scraper_delay_spin)

        self._scraper_wait_js_cb = QCheckBox("Wait for JavaScript to render")
        self._scraper_wait_js_cb.setChecked(
            bool(self.settings.get("scraper_wait_for_js", True))
        )
        scraper_form.addRow("", self._scraper_wait_js_cb)

        self._scraper_remove_overlays_cb = QCheckBox("Auto-remove cookie/ad overlays")
        self._scraper_remove_overlays_cb.setChecked(
            bool(self.settings.get("scraper_remove_overlays", True))
        )
        scraper_form.addRow("", self._scraper_remove_overlays_cb)

        self._scraper_css_selectors_edit = QLineEdit(
            str(self.settings.get("scraper_css_selectors", ""))
        )
        self._scraper_css_selectors_edit.setPlaceholderText(
            "e.g. div.chapter-content, article.entry-content (comma-separated)"
        )
        self._scraper_css_selectors_edit.setToolTip(
            "CSS selectors for the main chapter content block. Leave blank to use auto-detection."
        )
        scraper_form.addRow("Content CSS selectors:", self._scraper_css_selectors_edit)

        self._scraper_exclude_selectors_edit = QLineEdit(
            str(self.settings.get("scraper_exclude_selectors", ""))
        )
        self._scraper_exclude_selectors_edit.setPlaceholderText(
            "e.g. .ads, nav, footer (comma-separated)"
        )
        self._scraper_exclude_selectors_edit.setToolTip(
            "CSS selectors for page elements to strip before content extraction."
        )
        scraper_form.addRow("Exclude CSS selectors:", self._scraper_exclude_selectors_edit)

        inner.addWidget(scraper_group)

        self._phase1_llm_assist_cb = QCheckBox("Enable LLM assist during Phase-1 extraction")
        self._phase1_llm_assist_cb.setChecked(
            bool(self.settings.get("phase1_llm_assist_enabled", False))
        )
        self._phase1_llm_assist_cb.setToolTip(
            "When enabled, Pass-1 extraction asks the selected LLM for assistive "
            "dialogue/thought hints before Phase-2 classification."
        )
        inner.addWidget(self._phase1_llm_assist_cb)

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

    def _browse_kokoro_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Kokoro Model File", "", "ONNX files (*.onnx);;All files (*)"
        )
        if path:
            self._kokoro_model_path_input.setText(path)

    def _browse_kokoro_voices(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Kokoro Voices File", "", "BIN files (*.bin);;All files (*)"
        )
        if path:
            self._kokoro_voices_path_input.setText(path)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        self.settings.set("output_dir", self._output_dir_input.text().strip())
        self.settings.set("tts_backend_url", self._backend_url_input.text().strip())
        self.settings.set("kokoro_model_path", self._kokoro_model_path_input.text().strip())
        self.settings.set("kokoro_voices_path", self._kokoro_voices_path_input.text().strip())
        dialogue_llm_url = self._dialogue_llm_url_input.text().strip()
        dialogue_llm_model = self._dialogue_llm_model_input.currentText().strip()
        llm_provider = str(self._llm_provider_combo.currentData() or "ollama_local")
        self.settings.set("llm_provider", llm_provider)
        self.settings.set("llm_url", dialogue_llm_url)
        self.settings.set("llm_model", dialogue_llm_model)
        self.settings.set("llm_api_key", self._llm_api_key_input.text().strip())
        self.settings.set("dialogue_llm_url", dialogue_llm_url)  # backward compat
        self.settings.set("dialogue_llm_model", dialogue_llm_model)  # backward compat
        self.settings.set("narrator_voice", self._narrator_voice_combo.currentText())
        self.settings.set("default_male_voice", self._default_male_voice_combo.currentText())
        self.settings.set("default_female_voice", self._default_female_voice_combo.currentText())
        self.settings.set("tts_speed", self._tts_speed_spin.value())
        self.settings.set("character_confidence_threshold", self._char_confidence_spin.value())
        self.settings.set("phase1_llm_assist_enabled", self._phase1_llm_assist_cb.isChecked())
        # Scraper settings
        self.settings.set("scraper_method", self._scraper_method_combo.currentText())
        self.settings.set("scraper_use_browser_gui", self._scraper_use_gui_cb.isChecked())
        self.settings.set("scraper_manual_navigation", self._scraper_manual_nav_cb.isChecked())
        self.settings.set("scraper_manual_navigation_timeout_sec", self._scraper_manual_nav_timeout_spin.value())
        self.settings.set("scraper_max_index_pages", self._scraper_max_index_pages_spin.value())
        self.settings.set("scraper_browser_timeout_sec", self._scraper_browser_timeout_spin.value())
        self.settings.set("scraper_delay_ms", self._scraper_delay_spin.value())
        self.settings.set("scraper_wait_for_js", self._scraper_wait_js_cb.isChecked())
        self.settings.set("scraper_remove_overlays", self._scraper_remove_overlays_cb.isChecked())
        self.settings.set("scraper_css_selectors", self._scraper_css_selectors_edit.text().strip())
        self.settings.set("scraper_exclude_selectors", self._scraper_exclude_selectors_edit.text().strip())
        self.settings.save()
        self.log.log("Settings saved.", level="SUCCESS")

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
        from ebook_app.tts.tts_service_launcher import launch_tts_service
        from ebook_app.tts.tts_client import TTSClient

        url = self._backend_url_input.text().strip() or _DEFAULT_TTS_SERVICE_URL
        existing_health = TTSClient(base_url=url, timeout=1).health()
        if existing_health.get("status") == "ok":
            self._on_tts_test_result(existing_health)
            self.log.log("TTS server is already running; skipped launching a duplicate process.", level="INFO")
            return

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

    def _on_setup_kokoro_models(self) -> None:
        if self._kokoro_setup_thread and self._kokoro_setup_thread.isRunning():
            return
        if self._kokoro_setup_thread is not None:
            try:
                self._kokoro_setup_thread.result.disconnect(self._on_kokoro_setup_result)
            except RuntimeError:
                # Signal can already be disconnected when replacing a prior finished thread.
                pass
            self._kokoro_setup_thread.deleteLater()
        self._setup_kokoro_btn.setEnabled(False)
        self._svc_status_label.setText("⏳ Downloading Kokoro model files…")
        self._svc_status_label.setStyleSheet("")
        self._kokoro_setup_thread = _KokoroModelSetupThread(parent=self)
        self._kokoro_setup_thread.result.connect(self._on_kokoro_setup_result)
        self._kokoro_setup_thread.start()

    def _on_kokoro_setup_result(self, result: dict) -> None:
        self._setup_kokoro_btn.setEnabled(True)
        if result.get("status") == "ok":
            model_path = result.get("model_path", "")
            voices_path = result.get("voices_path", "")
            self._svc_status_label.setText(
                f"✅ Kokoro models downloaded: {model_path} and {voices_path}"
            )
            self._svc_status_label.setStyleSheet("color: green;")
            self.log.log(
                "Kokoro models downloaded and ready for TTS service.",
                level="INFO",
            )
            return
        self._svc_status_label.setText(
            f"🔴 Kokoro model setup failed: {result.get('detail', 'Unknown error')}"
        )
        self._svc_status_label.setStyleSheet("color: red;")
        self.log.log(
            f"Kokoro model setup failed: {result.get('detail', 'Unknown error')}",
            level="ERROR",
        )

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

    def _on_llm_provider_changed(self, *_args) -> None:
        provider = str(self._llm_provider_combo.currentData() or "ollama_local")
        is_local = provider == "ollama_local"
        self._refresh_llm_models_btn.setEnabled(is_local)
        self._llm_api_key_input.setPlaceholderText(
            "Optional for local Ollama" if is_local else "Required for external cloud APIs"
        )

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
        llm_provider = str(self._llm_provider_combo.currentData() or "ollama_local")
        llm_url = self._dialogue_llm_url_input.text().strip()
        model = self._dialogue_llm_model_input.currentText().strip()
        api_key = self._llm_api_key_input.text().strip()
        self._llm_status_label.setText("⏳ Checking LLM connection…")
        self._llm_status_label.setStyleSheet("")
        self._llm_troubleshoot_label.hide()
        self._llm_health_thread = _LlmHealthThread(llm_provider, llm_url, model, api_key, parent=self)
        self._llm_health_thread.result.connect(self._on_llm_health_result)
        self._llm_health_thread.start()

    def _on_llm_health_result(self, result: dict) -> None:
        if result.get("status") == "ok":
            provider = result.get("provider", "ollama_local")
            available_models = result.get("available_models", []) or []
            if available_models:
                current_text = self._dialogue_llm_model_input.currentText().strip()
                self._dialogue_llm_model_input.blockSignals(True)
                self._dialogue_llm_model_input.clear()
                self._dialogue_llm_model_input.addItems(sorted({str(m).strip() for m in available_models if str(m).strip()}))
                if current_text:
                    if self._dialogue_llm_model_input.findText(current_text) < 0:
                        self._dialogue_llm_model_input.addItem(current_text)
                    self._dialogue_llm_model_input.setCurrentText(current_text)
                self._dialogue_llm_model_input.blockSignals(False)
            if not result.get("model_configured", False):
                self._llm_status_label.setText(
                    "⚠ LLM reachable, but no model is configured in Settings."
                )
                self._llm_status_label.setStyleSheet("color: orange;")
            elif result.get("model_found", False):
                if provider == "external_cloud":
                    self._llm_status_label.setText("✅ External cloud API settings look valid.")
                else:
                    self._llm_status_label.setText("✅ Local LLM reachable and selected model is available.")
                self._llm_status_label.setStyleSheet("color: green;")
            else:
                model = result.get("model", "").strip() or _EMPTY_MODEL_LABEL
                self._llm_status_label.setText(
                    f"⚠ LLM reachable, but model '{model}' was not found."
                )
                self._llm_status_label.setStyleSheet("color: orange;")
            self._llm_troubleshoot_label.hide()
            return

        self._llm_status_label.setText("🔴 Could not connect to configured LLM.")
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
            "1) Confirm your configured provider/service is running and reachable.\n"
            "2) Check that the URL is correct and reachable from this machine.\n"
            "3) Verify the selected model is available to that provider.\n"
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
