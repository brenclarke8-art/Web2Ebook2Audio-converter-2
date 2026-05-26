# src/ebook_app/ui/pages/settings_page.py
"""Settings page — edit and persist application settings."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ebook_app.ui.pages._base_page import BasePage


class SettingsPage(BasePage):
    """Page for viewing and editing all persisted application settings.

    Changes are saved to disk when the user clicks *Save*.
    """

    def _build_ui(self) -> None:
        general_group = QGroupBox("General")
        form = QFormLayout(general_group)

        self._output_dir_input = QLineEdit(str(self.settings.get("output_dir", "")))
        form.addRow("Output directory:", self._output_dir_input)

        self._layout.addWidget(general_group)

        tts_group = QGroupBox("TTS")
        tts_form = QFormLayout(tts_group)

        self._kokoro_path_input = QLineEdit(str(self.settings.get("kokoro_cli_path", "")))
        tts_form.addRow("Kokoro CLI path:", self._kokoro_path_input)

        self._layout.addWidget(tts_group)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        self._layout.addLayout(btn_row)

        self._layout.addStretch()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        """Persist modified settings to disk."""
        self.settings.set("output_dir", self._output_dir_input.text().strip())
        self.settings.set("kokoro_cli_path", self._kokoro_path_input.text().strip())
        self.settings.save()
        self.log.log("Settings saved.", level="SUCCESS")
