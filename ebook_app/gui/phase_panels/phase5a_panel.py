# ebook_app/gui/phase_panels/phase5a_panel.py
"""Phase 5a panel — Character Identification."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QVBoxLayout, QWidget,
)

from ebook_app.gui.phase_panels._base_panel import BasePhasePanel


class Phase5aPanel(BasePhasePanel):
    PHASE_NAME = "Phase 5a — Character Identification"
    PHASE_DESCRIPTION = (
        "Discover character names from the segments and store them in the character database.\n"
        "Existing characters are updated; new ones are added."
    )

    def _build_content(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("Characters discovered in this chapter:"))
        self._list = QListWidget()
        layout.addWidget(self._list)
        return widget

    def show_characters(self, characters: list) -> None:
        self._list.clear()
        for c in characters:
            name = c.get("name", "?") if isinstance(c, dict) else getattr(c, "name", "?")
            gender = c.get("gender", "?") if isinstance(c, dict) else getattr(c, "gender", "?")
            self._list.addItem(QListWidgetItem(f"{name}  ({gender})"))
