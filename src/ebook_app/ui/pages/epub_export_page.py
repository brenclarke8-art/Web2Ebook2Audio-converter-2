# src/ebook_app/ui/pages/epub_export_page.py
"""EPUB Export page — configure EPUB metadata and trigger export."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ebook_app.ui.pages._base_page import BasePage


class EpubExportPage(BasePage):
    """Page for configuring EPUB metadata and exporting the final EPUB3 file.

    TODO: wire to EPUBService when implemented.
    """

    def _build_ui(self) -> None:
        meta_group = QGroupBox("EPUB Metadata")
        vbox = QVBoxLayout(meta_group)

        for label_text, attr_name, placeholder in [
            ("Title:",    "_title_input",    "My Novel"),
            ("Author:",   "_author_input",   "Author Name"),
            ("Language:", "_language_input", "en"),
            ("ISBN:",     "_isbn_input",     "978-0-000000-00-0"),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            widget = QLineEdit()
            widget.setPlaceholderText(placeholder)
            setattr(self, attr_name, widget)
            row.addWidget(widget)
            vbox.addLayout(row)

        self._layout.addWidget(meta_group)

        output_group = QGroupBox("Output")
        out_layout = QHBoxLayout(output_group)
        out_layout.addWidget(QLabel("Output file:"))
        self._output_file_input = QLineEdit()
        self._output_file_input.setPlaceholderText("output.epub")
        out_layout.addWidget(self._output_file_input)
        self._layout.addWidget(output_group)

        btn_row = QHBoxLayout()
        self._export_btn = QPushButton("Export EPUB3")
        self._export_btn.clicked.connect(self._on_export)
        btn_row.addWidget(self._export_btn)
        btn_row.addStretch()
        self._layout.addLayout(btn_row)

        self._layout.addStretch()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_export(self) -> None:
        """Placeholder: build the EPUB3 package from processed chapters."""
        title = self._title_input.text().strip() or "Untitled"
        author = self._author_input.text().strip() or "Unknown"
        self.log.log(
            f"Exporting EPUB3: '{title}' by {author} (not yet implemented)",
            level="INFO",
        )
        # TODO: start EPUBService.export(title, author, ...)
