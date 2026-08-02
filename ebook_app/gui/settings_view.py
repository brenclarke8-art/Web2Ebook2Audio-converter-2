# ebook_app/gui/settings_view.py
"""Settings tab — edit and persist application settings.

Sections
────────
  Pipeline Mode   — manual / semi_auto / auto (top, prominent)
  TTS             — backend URL, voice, speed, auto-start
  LLM             — provider, URL, model, API key, timeout, retries
  Translation     — enable/disable, target language
  Scraper         — method, timeouts, CSS selectors
  Voices          — narrator, default male, default female
  Output          — output directory
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
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
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_DEFAULT_TTS_SERVICE_URL = "http://127.0.0.1:5005"


class _ServiceHealthThread(QThread):
    result = Signal(dict)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        from ebook_app.tts.tts_client import TTSClient
        self.result.emit(TTSClient(base_url=self._url).health())


class _LlmHealthThread(QThread):
    result = Signal(dict)

    def __init__(self, llm_url: str, model: str, api_key: str = "", parent=None):
        super().__init__(parent)
        self._llm_url = llm_url.strip()
        self._model = model.strip()
        self._api_key = api_key.strip()

    def run(self) -> None:
        import requests
        from urllib.parse import urlparse, urlunparse

        try:
            parsed = urlparse(self._llm_url)
            tags_url = urlunparse(parsed._replace(path="/api/tags", query="", fragment=""))
            resp = requests.get(tags_url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            models = [m.get("name", "") for m in (data.get("models") or [])]
            model_ok = any(self._model.split(":")[0] in m for m in models) if self._model else bool(models)
            self.result.emit({"ok": model_ok, "models": models, "error": ""})
        except Exception as exc:
            self.result.emit({"ok": False, "models": [], "error": str(exc)})


class SettingsPage(QWidget):
    """Settings page widget — can be embedded in a tab or standalone."""

    def __init__(self, settings: Any, log: Any = None, project_manager: Any = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.log = log
        self._health_thread: Optional[_ServiceHealthThread] = None
        self._llm_thread: Optional[_LlmHealthThread] = None
        self._build_ui()

    # ─────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        scroll.setWidget(container)
        outer.addWidget(scroll)

        layout.addWidget(self._build_pipeline_mode_group())
        layout.addWidget(self._build_tts_group())
        layout.addWidget(self._build_llm_group())
        layout.addWidget(self._build_translation_group())
        layout.addWidget(self._build_scraper_group())
        layout.addWidget(self._build_voices_group())
        layout.addWidget(self._build_output_group())
        layout.addStretch()

        # Save button
        save_btn = QPushButton("💾 Save Settings")
        save_btn.setStyleSheet(
            "background-color: #2980b9; color: white; font-weight: bold; padding: 8px 20px;"
        )
        save_btn.clicked.connect(self._save_all)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        outer.addLayout(btn_row)

    # ── Pipeline mode ────────────────────────────────────────────────────

    def _build_pipeline_mode_group(self) -> QGroupBox:
        group = QGroupBox("Pipeline Mode")
        layout = QVBoxLayout(group)

        desc = QLabel(
            "<b>Manual</b>: pause after every phase to review output and confirm.\n"
            "<b>Semi-auto</b>: run phases 1–5b automatically; pause at Phase 6 and "
            "between chapters.\n"
            "<b>Auto</b>: run all phases and chapters without pausing."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(desc)

        self._mode_manual = QRadioButton("Manual (default — recommended)")
        self._mode_semi = QRadioButton("Semi-auto")
        self._mode_auto = QRadioButton("Auto")

        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self._mode_manual, 0)
        self._mode_group.addButton(self._mode_semi, 1)
        self._mode_group.addButton(self._mode_auto, 2)

        current = self.settings.get("pipeline_mode", "manual")
        if current == "semi_auto":
            self._mode_semi.setChecked(True)
        elif current == "auto":
            self._mode_auto.setChecked(True)
        else:
            self._mode_manual.setChecked(True)

        layout.addWidget(self._mode_manual)
        layout.addWidget(self._mode_semi)
        layout.addWidget(self._mode_auto)
        return group

    # ── TTS ──────────────────────────────────────────────────────────────

    def _build_tts_group(self) -> QGroupBox:
        group = QGroupBox("TTS Service")
        form = QFormLayout(group)

        self._tts_url_edit = QLineEdit(self.settings.get("tts_backend_url", _DEFAULT_TTS_SERVICE_URL))
        self._tts_autostart = QCheckBox("Auto-start TTS service on launch")
        self._tts_autostart.setChecked(bool(self.settings.get("tts_autostart_service", True)))
        self._tts_voice_edit = QLineEdit(self.settings.get("tts_voice", "af_heart"))
        self._tts_speed_spin = QDoubleSpinBox()
        self._tts_speed_spin.setRange(0.25, 4.0)
        self._tts_speed_spin.setSingleStep(0.1)
        self._tts_speed_spin.setValue(float(self.settings.get("tts_speed", 1.0)))

        check_row = QHBoxLayout()
        self._tts_status_label = QLabel("")
        check_btn = QPushButton("Check")
        check_btn.setFixedWidth(60)
        check_btn.clicked.connect(self._check_tts)
        check_row.addWidget(self._tts_url_edit, 1)
        check_row.addWidget(check_btn)
        check_row.addWidget(self._tts_status_label)

        form.addRow("Backend URL", check_row)
        form.addRow("", self._tts_autostart)
        form.addRow("Default voice", self._tts_voice_edit)
        form.addRow("Speed", self._tts_speed_spin)
        return group

    # ── LLM ──────────────────────────────────────────────────────────────

    def _build_llm_group(self) -> QGroupBox:
        group = QGroupBox("LLM Settings")
        form = QFormLayout(group)

        self._llm_url_edit = QLineEdit(self.settings.get("llm_url", ""))
        self._llm_model_edit = QLineEdit(self.settings.get("llm_model", ""))
        self._llm_api_key_edit = QLineEdit(self.settings.get("llm_api_key", ""))
        self._llm_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self._llm_timeout_spin = QSpinBox()
        self._llm_timeout_spin.setRange(10, 3600)
        self._llm_timeout_spin.setValue(int(self.settings.get("llm_timeout", 300)))
        self._llm_timeout_spin.setSuffix(" s")

        self._llm_retries_spin = QSpinBox()
        self._llm_retries_spin.setRange(0, 10)
        self._llm_retries_spin.setValue(int(self.settings.get("llm_retries", 1)))

        self._llm_preflight_check = QCheckBox("Run LLM preflight check on startup")
        self._llm_preflight_check.setChecked(bool(self.settings.get("llm_preflight_check", True)))

        llm_check_row = QHBoxLayout()
        self._llm_status_label = QLabel("")
        llm_check_btn = QPushButton("Check")
        llm_check_btn.setFixedWidth(60)
        llm_check_btn.clicked.connect(self._check_llm)
        llm_check_row.addWidget(self._llm_url_edit, 1)
        llm_check_row.addWidget(llm_check_btn)
        llm_check_row.addWidget(self._llm_status_label)

        form.addRow("LLM URL", llm_check_row)
        form.addRow("Model", self._llm_model_edit)
        form.addRow("API key", self._llm_api_key_edit)
        form.addRow("Timeout", self._llm_timeout_spin)
        form.addRow("Retries", self._llm_retries_spin)
        form.addRow("", self._llm_preflight_check)
        return group

    # ── Translation ───────────────────────────────────────────────────────

    def _build_translation_group(self) -> QGroupBox:
        group = QGroupBox("Translation (Phase 3)")
        form = QFormLayout(group)

        self._trans_enabled = QCheckBox("Enable translation")
        self._trans_enabled.setChecked(bool(self.settings.get("translation_enabled", False)))

        self._trans_lang_combo = QComboBox()
        langs = ["en", "fr", "de", "es", "it", "pt", "ja", "zh", "ko", "ru", "ar"]
        self._trans_lang_combo.addItems(langs)
        current = self.settings.get("translation_target_language", "en")
        idx = self._trans_lang_combo.findText(current)
        if idx >= 0:
            self._trans_lang_combo.setCurrentIndex(idx)

        form.addRow("", self._trans_enabled)
        form.addRow("Target language", self._trans_lang_combo)
        return group

    # ── Scraper ───────────────────────────────────────────────────────────

    def _build_scraper_group(self) -> QGroupBox:
        group = QGroupBox("Web Scraper")
        form = QFormLayout(group)

        self._scraper_method = QComboBox()
        self._scraper_method.addItems(["browser", "requests"])
        current_method = self.settings.get("scraper_method", "browser")
        idx = self._scraper_method.findText(current_method)
        if idx >= 0:
            self._scraper_method.setCurrentIndex(idx)

        self._scraper_max_pages = QSpinBox()
        self._scraper_max_pages.setRange(1, 500)
        self._scraper_max_pages.setValue(int(self.settings.get("scraper_max_index_pages", 50)))

        self._scraper_timeout = QSpinBox()
        self._scraper_timeout.setRange(5, 300)
        self._scraper_timeout.setValue(int(self.settings.get("scraper_browser_timeout_sec", 30)))
        self._scraper_timeout.setSuffix(" s")

        self._scraper_delay = QSpinBox()
        self._scraper_delay.setRange(0, 5000)
        self._scraper_delay.setValue(int(self.settings.get("scraper_delay_ms", 500)))
        self._scraper_delay.setSuffix(" ms")

        self._scraper_wait_js = QCheckBox("Wait for JavaScript")
        self._scraper_wait_js.setChecked(bool(self.settings.get("scraper_wait_for_js", True)))

        self._scraper_rm_overlays = QCheckBox("Remove overlays / popups")
        self._scraper_rm_overlays.setChecked(bool(self.settings.get("scraper_remove_overlays", True)))

        self._scraper_css_edit = QLineEdit(self.settings.get("scraper_css_selectors", ""))
        self._scraper_css_edit.setPlaceholderText("CSS selectors for content (optional)")

        self._scraper_excl_edit = QLineEdit(self.settings.get("scraper_exclude_selectors", ""))
        self._scraper_excl_edit.setPlaceholderText("CSS selectors to exclude (optional)")

        form.addRow("Scraper method", self._scraper_method)
        form.addRow("Max index pages", self._scraper_max_pages)
        form.addRow("Page timeout", self._scraper_timeout)
        form.addRow("Delay between requests", self._scraper_delay)
        form.addRow("", self._scraper_wait_js)
        form.addRow("", self._scraper_rm_overlays)
        form.addRow("Content selectors", self._scraper_css_edit)
        form.addRow("Exclude selectors", self._scraper_excl_edit)
        return group

    # ── Voices ────────────────────────────────────────────────────────────

    def _build_voices_group(self) -> QGroupBox:
        group = QGroupBox("Default Voices")
        form = QFormLayout(group)

        self._narrator_voice_edit = QLineEdit(self.settings.get("narrator_voice", "af_heart"))
        self._male_voice_edit = QLineEdit(self.settings.get("default_male_voice", "am_adam"))
        self._female_voice_edit = QLineEdit(self.settings.get("default_female_voice", "af_bella"))

        form.addRow("Narrator voice", self._narrator_voice_edit)
        form.addRow("Default male voice", self._male_voice_edit)
        form.addRow("Default female voice", self._female_voice_edit)
        return group

    # ── Output ────────────────────────────────────────────────────────────

    def _build_output_group(self) -> QGroupBox:
        group = QGroupBox("Output")
        form = QFormLayout(group)

        out_row = QHBoxLayout()
        self._output_dir_edit = QLineEdit(self.settings.get("output_dir", ""))
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_output_dir)
        out_row.addWidget(self._output_dir_edit)
        out_row.addWidget(browse_btn)
        form.addRow("Output directory", out_row)
        return group

    def _browse_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select output directory")
        if path:
            self._output_dir_edit.setText(path)

    # ─────────────────────────────────────────────────────────────────────
    # Save
    # ─────────────────────────────────────────────────────────────────────

    def _save_all(self) -> None:
        mode_id = self._mode_group.checkedId()
        mode = ["manual", "semi_auto", "auto"][mode_id]
        self.settings.set("pipeline_mode", mode)

        self.settings.set("tts_backend_url", self._tts_url_edit.text().strip())
        self.settings.set("tts_autostart_service", self._tts_autostart.isChecked())
        self.settings.set("tts_voice", self._tts_voice_edit.text().strip())
        self.settings.set("tts_speed", self._tts_speed_spin.value())

        self.settings.set("llm_url", self._llm_url_edit.text().strip())
        self.settings.set("llm_model", self._llm_model_edit.text().strip())
        self.settings.set("llm_api_key", self._llm_api_key_edit.text().strip())
        self.settings.set("llm_timeout", self._llm_timeout_spin.value())
        self.settings.set("llm_retries", self._llm_retries_spin.value())
        self.settings.set("llm_preflight_check", self._llm_preflight_check.isChecked())

        self.settings.set("translation_enabled", self._trans_enabled.isChecked())
        self.settings.set("translation_target_language", self._trans_lang_combo.currentText())

        self.settings.set("scraper_method", self._scraper_method.currentText())
        self.settings.set("scraper_max_index_pages", self._scraper_max_pages.value())
        self.settings.set("scraper_browser_timeout_sec", self._scraper_timeout.value())
        self.settings.set("scraper_delay_ms", self._scraper_delay.value())
        self.settings.set("scraper_wait_for_js", self._scraper_wait_js.isChecked())
        self.settings.set("scraper_remove_overlays", self._scraper_rm_overlays.isChecked())
        self.settings.set("scraper_css_selectors", self._scraper_css_edit.text().strip())
        self.settings.set("scraper_exclude_selectors", self._scraper_excl_edit.text().strip())

        self.settings.set("narrator_voice", self._narrator_voice_edit.text().strip())
        self.settings.set("default_male_voice", self._male_voice_edit.text().strip())
        self.settings.set("default_female_voice", self._female_voice_edit.text().strip())

        self.settings.set("output_dir", self._output_dir_edit.text().strip())

        if self.log:
            self.log.log("Settings saved.", "SUCCESS")

    # ─────────────────────────────────────────────────────────────────────
    # Service health checks
    # ─────────────────────────────────────────────────────────────────────

    def _check_tts(self) -> None:
        url = self._tts_url_edit.text().strip() or _DEFAULT_TTS_SERVICE_URL
        self._tts_status_label.setText("⏳")
        self._health_thread = _ServiceHealthThread(url, self)
        self._health_thread.result.connect(self._on_tts_health)
        self._health_thread.start()

    def _on_tts_health(self, result: dict) -> None:
        if result.get("status") == "ok":
            self._tts_status_label.setText("✅")
        else:
            self._tts_status_label.setText("❌")

    def _check_llm(self) -> None:
        url = self._llm_url_edit.text().strip()
        model = self._llm_model_edit.text().strip()
        key = self._llm_api_key_edit.text().strip()
        self._llm_status_label.setText("⏳")
        self._llm_thread = _LlmHealthThread(url, model, key, self)
        self._llm_thread.result.connect(self._on_llm_health)
        self._llm_thread.start()

    def _on_llm_health(self, result: dict) -> None:
        if result.get("ok"):
            self._llm_status_label.setText("✅")
        else:
            err = result.get("error", "")
            self._llm_status_label.setText(f"❌ {err[:40]}" if err else "❌")
