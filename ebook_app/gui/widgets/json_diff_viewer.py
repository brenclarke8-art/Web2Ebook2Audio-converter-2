# ebook_app/app/widgets/json_diff_viewer.py

from __future__ import annotations

import json
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QSyntaxHighlighter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel
)


class JSONDiffViewer(QWidget):
    """
    Side-by-side JSON diff viewer.
    Shows:
        - Pass-2 JSON on the left
        - Final JSON on the right
        - Highlights differences
        - Optional "Apply change" button per diff

    Emits:
        apply_change(key, value)
    """

    apply_change = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("JSON Diff (Pass‑2 vs Final)")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        # Side-by-side editors
        row = QHBoxLayout()
        layout.addLayout(row, 1)

        self.left_edit = QTextEdit()
        self.right_edit = QTextEdit()

        self.left_edit.setReadOnly(True)
        self.right_edit.setReadOnly(True)

        row.addWidget(self.left_edit, 1)
        row.addWidget(self.right_edit, 1)

        # Apply button
        self.btn_apply = QPushButton("Apply Selected Change → Final")
        self.btn_apply.clicked.connect(self._apply_selected_change)
        layout.addWidget(self.btn_apply)

        # Syntax highlighters
        self.left_highlighter = _JSONHighlighter(self.left_edit.document())
        self.right_highlighter = _JSONHighlighter(self.right_edit.document())

        # Internal diff data
        self.diff_map = {}  # key → (pass2_value, final_value)

    # ------------------------------------------------------------------
    def load_json(self, pass2_data: dict, final_data: dict):
        """Load two JSON objects and compute diffs."""
        self.left_edit.clear()
        self.right_edit.clear()
        self.diff_map.clear()

        # Pretty print
        left_text = json.dumps(pass2_data, indent=2, ensure_ascii=False)
        right_text = json.dumps(final_data, indent=2, ensure_ascii=False)

        self.left_edit.setPlainText(left_text)
        self.right_edit.setPlainText(right_text)

        # Compute diffs
        self._compute_diffs(pass2_data, final_data)

        # Highlight diffs
        self._highlight_diffs()

    # ------------------------------------------------------------------
    def _compute_diffs(self, a: dict, b: dict, prefix=""):
        """Recursively compute differences between two dicts."""
        for key in a.keys() | b.keys():
            full_key = f"{prefix}.{key}" if prefix else key

            if key not in a:
                self.diff_map[full_key] = ("<missing>", b[key])
            elif key not in b:
                self.diff_map[full_key] = (a[key], "<missing>")
            else:
                if isinstance(a[key], dict) and isinstance(b[key], dict):
                    self._compute_diffs(a[key], b[key], full_key)
                else:
                    if a[key] != b[key]:
                        self.diff_map[full_key] = (a[key], b[key])

    # ------------------------------------------------------------------
    def _highlight_diffs(self):
        """Highlight lines that differ."""
        left_cursor = self.left_edit.textCursor()
        right_cursor = self.right_edit.textCursor()

        diff_color_left = QColor("#ffcc80")   # orange
        diff_color_right = QColor("#80d8ff")  # light blue

        for key in self.diff_map.keys():
            # Highlight occurrences of the key in both editors
            self._highlight_key(self.left_edit, key, diff_color_left)
            self._highlight_key(self.right_edit, key, diff_color_right)

    def _highlight_key(self, editor: QTextEdit, key: str, color: QColor):
        cursor = editor.textCursor()
        fmt = QTextCharFormat()
        fmt.setBackground(color)

        text = editor.toPlainText()
        idx = text.find(f"\"{key.split('.')[-1]}\"")

        while idx != -1:
            cursor.setPosition(idx)
            cursor.movePosition(cursor.EndOfLine, cursor.KeepAnchor)
            cursor.mergeCharFormat(fmt)

            idx = text.find(f"\"{key.split('.')[-1]}\"", idx + 1)

    # ------------------------------------------------------------------
    def _apply_selected_change(self):
        """Apply the first diff found in the map (simple version)."""
        if not self.diff_map:
            return

        # For now, apply the first diff
        key, (pass2_val, _) = next(iter(self.diff_map.items()))
        self.apply_change.emit(key, pass2_val)

    # ------------------------------------------------------------------
    def clear(self):
        self.left_edit.clear()
        self.right_edit.clear()
        self.diff_map.clear()


# ======================================================================
# JSON Syntax Highlighter
# ======================================================================

class _JSONHighlighter(QSyntaxHighlighter):
    """Simple JSON syntax highlighter."""

    def __init__(self, document):
        super().__init__(document)

        self.key_format = QTextCharFormat()
        self.key_format.setForeground(QColor("#ffab40"))

        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#80cbc4"))

        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor("#82b1ff"))

        self.bool_format = QTextCharFormat()
        self.bool_format.setForeground(QColor("#f48fb1"))

        self.null_format = QTextCharFormat()
        self.null_format.setForeground(QColor("#b0bec5"))

    def highlightBlock(self, text: str):
        i = 0
        while i < len(text):
            ch = text[i]

            # Keys: "something":
            if ch == '"':
                start = i
                i += 1
                while i < len(text) and text[i] != '"':
                    i += 1
                i += 1

                # Check if followed by colon → key
                if i < len(text) and text[i] == ":":
                    self.setFormat(start, i - start, self.key_format)
                else:
                    self.setFormat(start, i - start, self.string_format)

            # Numbers
            elif ch.isdigit() or (ch == "-" and i + 1 < len(text) and text[i + 1].isdigit()):
                start = i
                i += 1
                while i < len(text) and (text[i].isdigit() or text[i] in ".eE+-"):
                    i += 1
                self.setFormat(start, i - start, self.number_format)

            # Booleans
            elif text.startswith("true", i) or text.startswith("false", i):
                length = 4 if text.startswith("true", i) else 5
                self.setFormat(i, length, self.bool_format)
                i += length

            # Null
            elif text.startswith("null", i):
                self.setFormat(i, 4, self.null_format)
                i += 4

            else:
                i += 1
