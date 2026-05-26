# src/ebook_app/ui/pages/translator_page.py
"""Translator page — configure and run batch chapter translation."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ebook_app.ui.pages._base_page import BasePage


_PROVIDERS = ["google", "deepl", "microsoft", "libre"]
_LANGUAGES = ["en", "es", "fr", "de", "pt", "ja", "ko", "zh-CN"]


class TranslatorPage(BasePage):
    """Page for choosing a translation provider and triggering batch translation.

    TODO: wire to TranslationService when implemented.
    """

    def _build_ui(self) -> None:
        config_group = QGroupBox("Translation Settings")
        vbox = QVBoxLayout(config_group)

        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("Provider:"))
        self._provider_combo = QComboBox()
        self._provider_combo.addItems(_PROVIDERS)
        current_provider = self.settings.get("translator_provider", "google")
        if current_provider in _PROVIDERS:
            self._provider_combo.setCurrentText(current_provider)
        provider_row.addWidget(self._provider_combo)
        provider_row.addStretch()
        vbox.addLayout(provider_row)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Target language:"))
        self._lang_combo = QComboBox()
        self._lang_combo.addItems(_LANGUAGES)
        current_lang = self.settings.get("translator_target_lang", "en")
        if current_lang in _LANGUAGES:
            self._lang_combo.setCurrentText(current_lang)
        lang_row.addWidget(self._lang_combo)
        lang_row.addStretch()
        vbox.addLayout(lang_row)

        self._layout.addWidget(config_group)

        btn_row = QHBoxLayout()
        self._translate_btn = QPushButton("Translate Chapters")
        self._translate_btn.clicked.connect(self._on_translate)
        btn_row.addWidget(self._translate_btn)
        btn_row.addStretch()
        self._layout.addLayout(btn_row)

        self._layout.addStretch()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_translate(self) -> None:
        """Placeholder: translate all scraped chapters."""
        provider = self._provider_combo.currentText()
        lang = self._lang_combo.currentText()
        self.settings.set("translator_provider", provider)
        self.settings.set("translator_target_lang", lang)
        self.log.log(
            f"Translating with '{provider}' → '{lang}'… (not yet implemented)",
            level="INFO",
        )
        # TODO: start TranslationService.translate_all(provider, lang)
