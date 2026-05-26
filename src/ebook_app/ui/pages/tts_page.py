# src/ebook_app/ui/pages/tts_page.py
"""TTS page — configure voice settings and trigger speech synthesis."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ebook_app.ui.pages._base_page import BasePage


_VOICES = [
    "af_heart", "af_bella", "af_sarah",
    "am_adam", "am_michael",
    "bf_emma", "bf_isabella",
    "bm_george", "bm_lewis",
]


class TTSPage(BasePage):
    """Page for configuring TTS voice, speed, and Kokoro CLI path.

    TODO: wire to TTSService when implemented.
    """

    def _build_ui(self) -> None:
        # Kokoro CLI path
        cli_group = QGroupBox("Kokoro CLI")
        cli_layout = QHBoxLayout(cli_group)
        cli_layout.addWidget(QLabel("Executable path:"))
        self._cli_path_input = QLineEdit()
        self._cli_path_input.setPlaceholderText("/path/to/kokoro-onnx")
        self._cli_path_input.setText(str(self.settings.get("kokoro_cli_path", "")))
        cli_layout.addWidget(self._cli_path_input)
        self._layout.addWidget(cli_group)

        # Voice settings
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

        # Action buttons
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

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_batch_tts(self) -> None:
        """Placeholder: synthesise audio for all chapters."""
        voice = self._voice_combo.currentText()
        speed = self._speed_spin.value()
        self.settings.set("tts_voice", voice)
        self.settings.set("tts_speed", speed)
        self.log.log(
            f"Batch TTS — voice='{voice}', speed={speed} (not yet implemented)",
            level="INFO",
        )
        # TODO: start TTSService.batch_synthesise(voice, speed)

    def _on_preview(self) -> None:
        """Placeholder: synthesise a short preview sample."""
        self.log.log("TTS preview not yet implemented.", level="INFO")
        # TODO: TTSService.preview(voice, speed)
