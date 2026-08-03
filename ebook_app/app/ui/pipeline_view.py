# ebook_app/app/ui/pipeline_view.py
"""Pipeline page — embeds the full pipeline wizard."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout

from ebook_app.app.ui.base_view import BasePage


class PipelinePage(BasePage):
    """Page that hosts the end-to-end pipeline wizard."""

    def _build_ui(self) -> None:
        try:
            from ebook_app.gui.pipeline_wizard import PipelineWizard

            wizard = PipelineWizard(self.settings, self.project_manager)
            wizard.log_message.connect(
                lambda msg, lvl: self.log.log(msg, lvl) if self.log else None
            )
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.addWidget(wizard)
        except Exception as exc:  # pragma: no cover
            self._layout.addWidget(
                QLabel(f"⚠ Pipeline wizard failed to load: {exc}")
            )
