# src/ebook_app/ui/pages/tts_page.py
"""TTS page — configure voice settings and trigger speech synthesis."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ebook_app.models.tts_engine_cli import DEFAULT_MODELS_DIR, TTSEngine, _resolve_model_paths
from ebook_app.models.voice_catalog import KOKORO_VOICE_CATALOG
from ebook_app.ui.pages._base_page import BasePage

_DEFAULT_TTS_SERVICE_URL = "http://127.0.0.1:5005"

_VOICES = list(KOKORO_VOICE_CATALOG.keys())


class _HealthCheckThread(QThread):
    """Background thread to probe the remote TTS service health endpoint."""

    result = Signal(dict)  # emits the health JSON dict

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        from ebook_app.services.tts_client import TTSClient

        client = TTSClient(base_url=self._url)
        self.result.emit(client.health())


class TTSPage(BasePage):
    """Page for configuring TTS voice and speed, and triggering synthesis."""

    def _build_ui(self) -> None:
        # ── Model / Service status ──────────────────────────────────────
        status_group = QGroupBox("TTS Backend Status")
        status_layout = QHBoxLayout(status_group)
        self._status_label = QLabel()
        self._refresh_status()
        status_layout.addWidget(self._status_label)
        status_layout.addStretch()
        self._refresh_status_btn = QPushButton("Refresh")
        self._refresh_status_btn.clicked.connect(self._refresh_status)
        status_layout.addWidget(self._refresh_status_btn)
        self._layout.addWidget(status_group)

        # ── Voice Settings ─────────────────────────────────────────────
        voice_group = QGroupBox("Voice Settings")
        vbox = QVBoxLayout(voice_group)

        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("Voice:"))
        self._voice_combo = QComboBox()
        self._voice_combo.addItems(_VOICES)
        current_voice = self.settings.get("tts_voice", "af_heart")
        if current_voice in _VOICES:
            self._voice_combo.setCurrentText(current_voice)
        voice_row.addWidget(self._voice_combo)
        voice_row.addStretch()
        vbox.addLayout(voice_row)

        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Speed:"))
        self._speed_spin = QDoubleSpinBox()
        self._speed_spin.setRange(0.5, 2.0)
        self._speed_spin.setSingleStep(0.05)
        self._speed_spin.setValue(float(self.settings.get("tts_speed", 1.0)))
        speed_row.addWidget(self._speed_spin)
        speed_row.addStretch()
        vbox.addLayout(speed_row)

        self._layout.addWidget(voice_group)

        # ── Action buttons ─────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._tts_batch_btn = QPushButton("Batch TTS (all chapters)")
        self._tts_preview_btn = QPushButton("Preview voice")
        self._tts_batch_btn.clicked.connect(self._on_batch_tts)
        self._tts_preview_btn.clicked.connect(self._on_preview)
        btn_row.addWidget(self._tts_batch_btn)
        btn_row.addWidget(self._tts_preview_btn)
        btn_row.addStretch()
        self._layout.addLayout(btn_row)

        self._layout.addStretch()
        self._health_thread: _HealthCheckThread | None = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _refresh_status(self) -> None:
        mode = self.settings.get("tts_backend_mode", "local")

        if mode == "remote":
            self._status_label.setText("⏳ Checking TTS service…")
            self._status_label.setStyleSheet("")
            url = self.settings.get("tts_backend_url", _DEFAULT_TTS_SERVICE_URL)
            if self._health_thread and self._health_thread.isRunning():
                return
            # Discard old thread before creating a new one to avoid signal leaks.
            if self._health_thread is not None:
                self._health_thread.result.disconnect(self._on_health_result)
                self._health_thread.deleteLater()
            self._health_thread = _HealthCheckThread(url, parent=self)
            self._health_thread.result.connect(self._on_health_result)
            self._health_thread.start()
        else:
            # Local mode — check model files on disk
            model_path, voices_path = _resolve_model_paths(
                self.settings.get("kokoro_model_path") or None,
                self.settings.get("kokoro_voices_path") or None,
            )
            if model_path.exists() and voices_path.exists():
                self._status_label.setText("✅ Kokoro models ready (local mode).")
                self._status_label.setStyleSheet("color: green;")
            else:
                self._status_label.setText(
                    "⚠ Kokoro models not found. Go to Settings → Download Models."
                )
                self._status_label.setStyleSheet("color: orange;")

    def _on_health_result(self, health: dict) -> None:
        status = health.get("status", "unknown")
        models_ready = health.get("models_ready", False)
        url = self.settings.get("tts_backend_url", _DEFAULT_TTS_SERVICE_URL)

        if status == "unreachable":
            self._status_label.setText(
                f"🔴 TTS service not running at {url}. "
                "Start it with: uvicorn tts_server:app --port 5005"
            )
            self._status_label.setStyleSheet("color: red;")
        elif status == "ok" and models_ready:
            self._status_label.setText(f"✅ TTS service ready at {url} (remote mode).")
            self._status_label.setStyleSheet("color: green;")
        elif status == "ok" and not models_ready:
            model_path = health.get("model_path", "")
            self._status_label.setText(
                f"⚠ TTS service running but models not found at {model_path}."
            )
            self._status_label.setStyleSheet("color: orange;")
        else:
            detail = health.get("detail", "")
            self._status_label.setText(f"⚠ TTS service error: {detail}")
            self._status_label.setStyleSheet("color: orange;")

    def _save_voice_settings(self) -> None:
        self.settings.set("tts_voice", self._voice_combo.currentText())
        self.settings.set("tts_speed", self._speed_spin.value())

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_batch_tts(self) -> None:
        self._save_voice_settings()
        voice = self._voice_combo.currentText()
        speed = self._speed_spin.value()
        self.log.log(
            f"Batch TTS — voice='{voice}', speed={speed} (not yet implemented)",
            level="INFO",
        )
        # TODO: start TTSService.batch_synthesise(voice, speed)

    def _on_preview(self) -> None:
        self._save_voice_settings()
        voice = self._voice_combo.currentText()
        speed = self._speed_spin.value()
        mode = self.settings.get("tts_backend_mode", "local")
        try:
            if mode == "remote":
                from ebook_app.services.tts_client import TTSClient

                client = TTSClient(
                    output_dir=self.settings.output_dir,
                    base_url=self.settings.get(
                        "tts_backend_url", _DEFAULT_TTS_SERVICE_URL
                    ),
                )
                self.log.log(
                    f"Generating preview via TTS service for voice '{voice}'…",
                    level="INFO",
                )
                path = client.generate_preview(voice=voice, speed=speed)
            else:
                engine = TTSEngine(
                    output_dir=self.settings.output_dir,
                    model_path=self.settings.get("kokoro_model_path") or None,
                    voices_path=self.settings.get("kokoro_voices_path") or None,
                )
                self.log.log(
                    f"Generating preview for voice '{voice}'…", level="INFO"
                )
                path = engine.generate_preview(voice=voice, speed=speed)

            self.log.log(f"Preview saved: {path}", level="SUCCESS")
        except Exception as exc:
            self.log.log(f"Preview failed: {exc}", level="ERROR")

