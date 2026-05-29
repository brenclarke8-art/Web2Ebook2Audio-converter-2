from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QTextEdit,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QSplitter,
)
from PySide6.QtGui import QTextCharFormat, QColor
from PySide6.QtCore import Qt


class EpubChapterPreviewDialog(QDialog):
    """Advanced EPUB preview dialog with:
    - Color-coded semantic segments
    - Split view (text vs JSON)
    - Chapter navigation
    - Jump-to-segment audio sync
    """

    COLORS = {
        "narration": QColor("#CCCCCC"),
        "dialogue": QColor("#A0D8FF"),
        "thought": QColor("#FFD6A5"),
        "system": QColor("#E0E0E0"),
    }

    def __init__(self, parent, work_dir: Path, chapter_index: int, max_chapters: int):
        super().__init__(parent)
        self._work_dir = work_dir
        self._chapter_index = chapter_index
        self._max_chapters = max_chapters
        self._chapter_id = f"ch{chapter_index:03d}"

        self.setWindowTitle(f"EPUB Preview — Chapter {chapter_index + 1}")
        self.resize(1200, 800)

        self._build_ui()
        self._load_content()

    # ------------------------------------------------------------
    # UI
    # ------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Navigation row
        nav_row = QHBoxLayout()
        self._btn_prev = QPushButton("← Prev")
        self._btn_next = QPushButton("Next →")
        self._btn_prev.clicked.connect(self._go_prev)
        self._btn_next.clicked.connect(self._go_next)
        nav_row.addWidget(self._btn_prev)
        nav_row.addWidget(self._btn_next)
        layout.addLayout(nav_row)

        # Split view
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # Left: text view
        self._text_view = QTextEdit()
        self._text_view.setReadOnly(True)
        splitter.addWidget(self._text_view)

        # Right: JSON + segment list
        right_panel = QVBoxLayout()
        right_widget = QDialog()
        right_widget.setLayout(right_panel)
        splitter.addWidget(right_widget)

        # Segment list
        self._segment_list = QListWidget()
        self._segment_list.itemClicked.connect(self._on_segment_clicked)
        right_panel.addWidget(self._segment_list)

        # JSON view
        self._json_view = QTextEdit()
        self._json_view.setReadOnly(True)
        right_panel.addWidget(self._json_view)

        # Metadata
        self._meta_label = QLabel()
        self._meta_label.setWordWrap(True)
        layout.addWidget(self._meta_label)

    # ------------------------------------------------------------
    # Load content
    # ------------------------------------------------------------
    def _load_content(self) -> None:
        ch_id = self._chapter_id
        wd = self._work_dir

        # Load cleaned text
        cleaned_final = wd / f"{ch_id}_cleaned_final.txt"
        cleaned = wd / f"{ch_id}_cleaned.txt"

        text = ""
        if cleaned_final.exists():
            text = cleaned_final.read_text(encoding="utf-8")
        elif cleaned.exists():
            text = cleaned.read_text(encoding="utf-8")
        else:
            text = "[No cleaned text found]"

        self._text_view.setPlainText(text)

        # Load semantic JSON
        info_file = wd / ch_id / "chapter_info.json"
        if info_file.exists():
            data = json.loads(info_file.read_text(encoding="utf-8"))
            pretty = json.dumps(data, indent=2, ensure_ascii=False)
            self._json_view.setPlainText(pretty)
            self._load_segments(data.get("segments", []))
        else:
            self._json_view.setPlainText("[chapter_info.json not found]")

        # Metadata
        self._meta_label.setText(
            f"Work dir: {wd}\n"
            f"Chapter ID: {ch_id}\n"
        )

    # ------------------------------------------------------------
    # Segment list + color coding
    # ------------------------------------------------------------
    def _load_segments(self, segments):
        self._segment_list.clear()

        cursor = self._text_view.textCursor()
        doc = self._text_view.document()

        for idx, seg in enumerate(segments):
            text = seg.get("text", "").strip()
            seg_type = seg.get("type", "narration")
            speaker = seg.get("speaker", "narrator")

            item = QListWidgetItem(f"{idx}: [{seg_type}] {speaker} — {text[:40]}...")
            item.setData(Qt.UserRole, idx)
            self._segment_list.addItem(item)

            # Color highlight in text
            fmt = QTextCharFormat()
            fmt.setBackground(self.COLORS.get(seg_type, QColor("#FFFFFF")))

            # Find and highlight text
            cursor = doc.find(text, cursor)
            if cursor.isNull():
                continue
            cursor.mergeCharFormat(fmt)

    # ------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------
    def _go_prev(self):
        if self._chapter_index > 0:
            self._chapter_index -= 1
            self._chapter_id = f"ch{self._chapter_index:03d}"
            self._load_content()

    def _go_next(self):
        if self._chapter_index < self._max_chapters - 1:
            self._chapter_index += 1
            self._chapter_id = f"ch{self._chapter_index:03d}"
            self._load_content()

    # ------------------------------------------------------------
    # Jump to segment → sync with audio preview
    # ------------------------------------------------------------
    def _on_segment_clicked(self, item: QListWidgetItem):
        seg_index = item.data(Qt.UserRole)

        # Call back into main window
        if hasattr(self.parent(), "play_segment_preview"):
            self.parent().play_segment_preview(self._chapter_index, seg_index)
