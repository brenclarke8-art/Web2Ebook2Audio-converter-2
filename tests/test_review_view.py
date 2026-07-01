from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from types import ModuleType


class _DummyWidget:
    def __init__(self, *args, **kwargs) -> None:
        pass


sys.modules.setdefault("PySide6", ModuleType("PySide6"))
qtcore = ModuleType("PySide6.QtCore")
qtcore.QThread = _DummyWidget
qtcore.Signal = lambda *args, **kwargs: None
qtcore.Qt = SimpleNamespace(
    ItemFlag=SimpleNamespace(ItemIsEnabled=1),
)
sys.modules["PySide6.QtCore"] = qtcore

qtwidgets = ModuleType("PySide6.QtWidgets")
for name in [
    "QAbstractItemView",
    "QComboBox",
    "QGroupBox",
    "QHBoxLayout",
    "QHeaderView",
    "QLabel",
    "QMessageBox",
    "QPlainTextEdit",
    "QPushButton",
    "QSplitter",
    "QTableWidget",
    "QTableWidgetItem",
    "QTabWidget",
    "QVBoxLayout",
    "QWidget",
]:
    setattr(qtwidgets, name, _DummyWidget)
sys.modules["PySide6.QtWidgets"] = qtwidgets

base_page = ModuleType("ebook_app.app.ui.base_view")
base_page.BasePage = type("BasePage", (), {})
sys.modules["ebook_app.app.ui.base_view"] = base_page

from ebook_app.app.ui.review_view import ReviewPage


class _FakeCombo:
    def __init__(self) -> None:
        self.items: list[tuple[str, str]] = []
        self.current_index: int | None = None
        self.blocked: list[bool] = []

    def blockSignals(self, blocked: bool) -> None:
        self.blocked.append(blocked)

    def clear(self) -> None:
        self.items.clear()

    def addItem(self, label: str, userData=None) -> None:
        self.items.append((label, userData))

    def count(self) -> int:
        return len(self.items)

    def setCurrentIndex(self, index: int) -> None:
        self.current_index = index


class _FakeTextEdit:
    def __init__(self) -> None:
        self.value = ""

    def clear(self) -> None:
        self.value = ""

    def setPlainText(self, value: str) -> None:
        self.value = value


class _FakeLog:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def log(self, message: str, level: str = "INFO") -> None:
        self.messages.append((message, level))


def test_load_chapter_list_only_shows_chapters_with_scrape_output(tmp_path) -> None:
    work_dir = tmp_path / "pipeline_work"
    work_dir.mkdir()
    (work_dir / "chapters_raw.json").write_text(
        json.dumps(
            [
                {"title": "Chapter 1", "source": "https://example.com/ch1"},
                {"title": "Chapter 2", "source": "https://example.com/ch2"},
                {"title": "Chapter 3", "source": "https://example.com/ch3"},
            ]
        ),
        encoding="utf-8",
    )
    (work_dir / "ch2_raw.txt").write_text("scraped chapter 2", encoding="utf-8")
    (work_dir / "ch3_cleaned.txt").write_text("cleaned chapter 3", encoding="utf-8")

    changed_indexes: list[int] = []
    combo = _FakeCombo()
    page = SimpleNamespace(
        _chapter_combo=combo,
        _work_dir=lambda: work_dir,
        _on_chapter_combo_changed=lambda index: changed_indexes.append(index),
        _chapter_has_scrape_output=lambda chapter_id, chapter, root: ReviewPage._chapter_has_scrape_output(
            chapter_id, chapter, root
        ),
        log=_FakeLog(),
    )

    ReviewPage._load_chapter_list(page)

    assert combo.items == [
        ("ch2 — Chapter 2", "ch2"),
        ("ch3 — Chapter 3", "ch3"),
    ]
    assert combo.current_index == 0
    assert changed_indexes == [0]


def test_load_scraped_text_falls_back_to_phase2_raw_file(tmp_path) -> None:
    work_dir = tmp_path / "pipeline_work"
    work_dir.mkdir()
    raw_text = "Recovered scraped text"
    (work_dir / "ch2_raw.txt").write_text(raw_text, encoding="utf-8")

    scraped_view = _FakeTextEdit()
    page = SimpleNamespace(_scraped_view=scraped_view)

    ReviewPage._load_scraped_text(page, "ch2", work_dir)

    assert scraped_view.value == raw_text
