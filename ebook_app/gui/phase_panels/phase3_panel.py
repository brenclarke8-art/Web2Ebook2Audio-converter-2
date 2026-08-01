# ebook_app/gui/phase_panels/phase3_panel.py
"""Phase 3 panel — Translation (optional)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QLabel, QWidget,
)

from ebook_app.gui.phase_panels._base_panel import BasePhasePanel


class Phase3Panel(BasePhasePanel):
    PHASE_NAME = "Phase 3 — Translation (Optional)"
    PHASE_DESCRIPTION = (
        "Optionally translate the chapter text into the target language using the LLM.\n"
        "Disable this phase if your source is already in the target language."
    )

    def _build_content(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)

        self._enabled_check = QCheckBox("Enable translation")
        self._enabled_check.setChecked(
            bool(self.settings.get("translation_enabled", False))
        )
        form.addRow("", self._enabled_check)

        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["en", "fr", "de", "es", "it", "pt", "ja", "zh", "ko"])
        current_lang = self.settings.get("translation_target_language", "en")
        idx = self._lang_combo.findText(current_lang)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)
        form.addRow("Target language", self._lang_combo)

        return widget

    def get_phase_kwargs(self) -> dict:
        return {}   # settings are read directly by Phase3Translation from SettingsManager
