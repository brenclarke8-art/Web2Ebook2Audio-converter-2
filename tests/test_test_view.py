"""
Tests for:
  - TestPage GUI page (widget construction, URL/chapter controls)
  - extract_main_content_by_structure (anti-scrape HTML extractor)
"""
from __future__ import annotations

import sys
import types
from types import ModuleType


# ---------------------------------------------------------------------------
# Minimal PySide6 stubs so the test can run without a display
# ---------------------------------------------------------------------------

def _install_pyside6_stubs():
    """Register bare-minimum PySide6 stubs before any ebook_app import."""

    class _Signal:
        def __init__(self, *args, **kwargs):
            pass
        def connect(self, *a, **kw):
            pass
        def emit(self, *a, **kw):
            pass

    class _Widget:
        def __init__(self, *args, **kwargs):
            self._children = []
            self._layout = None
            self.clicked = _Signal()
            self.readyReadStandardOutput = _Signal()
            self.readyReadStandardError = _Signal()
            self.finished = _Signal()
        def setStyleSheet(self, *a, **kw): pass
        def setReadOnly(self, *a, **kw): pass
        def setPlaceholderText(self, *a, **kw): pass
        def setToolTip(self, *a, **kw): pass
        def setCheckState(self, *a, **kw): pass
        def setChecked(self, *a, **kw): pass
        def setRange(self, *a, **kw): pass
        def setValue(self, *a, **kw): pass
        def value(self): return 1
        def text(self): return ""
        def isChecked(self): return True
        def checkState(self): return 2  # Qt.Checked = 2
        def flags(self): return 0
        def setFlags(self, *a, **kw): pass
        def addWidget(self, *a, **kw): pass
        def addLayout(self, *a, **kw): pass
        def addStretch(self, *a, **kw): pass
        def addItem(self, *a, **kw): pass
        def count(self): return 0
        def item(self, i): return None
        def setContentsMargins(self, *a, **kw): pass
        def setSpacing(self, *a, **kw): pass
        def setSizes(self, *a, **kw): pass
        def setSelectionMode(self, *a, **kw): pass
        def append(self, *a, **kw): pass
        def clear(self, *a, **kw): pass
        def setText(self, *a, **kw): pass
        def state(self): return 0  # QProcess.NotRunning

    class _QVBoxLayout(_Widget):
        def __init__(self, parent=None):
            super().__init__()

    class _QHBoxLayout(_Widget):
        def __init__(self, parent=None):
            super().__init__()

    class _QListWidget(_Widget):
        NoSelection = 0
        MultiSelection = 2
        def __init__(self, *a, **kw):
            super().__init__()

    class _QSplitter(_Widget):
        def __init__(self, *a, **kw):
            super().__init__()

    class _QListWidgetItem(_Widget):
        def __init__(self, *a, **kw):
            super().__init__()

    class _QProcess(_Widget):
        NotRunning = 0
        def __init__(self, parent=None):
            super().__init__()
            self.readyReadStandardOutput = _Signal()
            self.readyReadStandardError = _Signal()
            self.finished = _Signal()
        def setProcessEnvironment(self, *a, **kw): pass
        def start(self, *a, **kw): pass

    # PySide6 package stub
    pyside6 = sys.modules.setdefault("PySide6", ModuleType("PySide6"))

    qtcore = ModuleType("PySide6.QtCore")
    qtcore.QObject = object
    qtcore.Signal = _Signal
    qtcore.Qt = types.SimpleNamespace(
        Horizontal=1,
        ItemIsUserCheckable=16,
        Checked=2,
        Unchecked=0,
        BottomDockWidgetArea=8,
    )
    qtcore.QProcess = _QProcess
    qtcore.QProcessEnvironment = lambda: _Widget()
    sys.modules["PySide6.QtCore"] = qtcore

    qtwidgets = ModuleType("PySide6.QtWidgets")
    for name in [
        "QCheckBox", "QComboBox", "QFormLayout", "QGroupBox",
        "QHBoxLayout", "QLabel", "QLineEdit", "QListWidget",
        "QMessageBox", "QPushButton", "QScrollArea", "QSpinBox",
        "QSplitter", "QTextEdit", "QVBoxLayout", "QWidget",
    ]:
        setattr(qtwidgets, name, _Widget)
    qtwidgets.QHBoxLayout = _QHBoxLayout
    qtwidgets.QVBoxLayout = _QVBoxLayout
    qtwidgets.QSplitter = _QSplitter
    qtwidgets.QListWidget = _QListWidget
    qtwidgets.QListWidgetItem = _QListWidgetItem
    sys.modules["PySide6.QtWidgets"] = qtwidgets

    # Stub base_view so it doesn't try to import real Qt
    base_view_mod = ModuleType("ebook_app.app.ui.base_view")

    class _BasePage:
        def __init__(self, *, settings=None, log=None, project_manager=None, parent=None):
            self.settings = settings
            self.log = log
            self.project_manager = project_manager
            self._layout = _QVBoxLayout()
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)
            self._build_ui()

        def _build_ui(self):
            raise NotImplementedError

    base_view_mod.BasePage = _BasePage
    sys.modules["ebook_app.app.ui.base_view"] = base_view_mod
    # Also register app.state stubs if needed
    sys.modules.setdefault("ebook_app.app.state.settings_manager", ModuleType("ebook_app.app.state.settings_manager"))
    sys.modules.setdefault("ebook_app.app.state.book_state", ModuleType("ebook_app.app.state.book_state"))
    sys.modules.setdefault("ebook_app.app.ui.logs_viewer", ModuleType("ebook_app.app.ui.logs_viewer"))


_install_pyside6_stubs()

# Now safe to import the module under test
from ebook_app.app.ui.test_view import TestPage, _discover_test_files, _repo_root  # noqa: E402
from ebook_app.text.parse.html_cleaner import extract_main_content_by_structure  # noqa: E402


# ---------------------------------------------------------------------------
# TestPage construction tests
# ---------------------------------------------------------------------------

class _DummyLog:
    def log(self, msg, level="INFO"):
        pass


def _make_page():
    return TestPage(settings=None, log=_DummyLog())


def test_test_page_instantiates():
    """TestPage can be constructed without a display."""
    page = _make_page()
    assert page is not None


def test_test_page_has_url_edit():
    """TestPage exposes a URL input control."""
    page = _make_page()
    assert hasattr(page, "_url_edit")


def test_test_page_has_index_page_spin():
    """TestPage has index page number spinbox."""
    page = _make_page()
    assert hasattr(page, "_index_page_spin")


def test_test_page_has_chapter_spin():
    """TestPage has chapter number spinbox."""
    page = _make_page()
    assert hasattr(page, "_chapter_spin")


def test_test_page_has_test_list():
    """TestPage has a test file list widget."""
    page = _make_page()
    assert hasattr(page, "_test_list")


def test_test_page_has_output_log():
    """TestPage has an output QTextEdit."""
    page = _make_page()
    assert hasattr(page, "_output")


def test_repo_root_returns_path_with_pyproject():
    """_repo_root() resolves to the directory containing pyproject.toml."""
    from pathlib import Path
    root = _repo_root()
    assert (root / "pyproject.toml").exists(), f"pyproject.toml not found at {root}"


def test_discover_test_files_finds_tests():
    """_discover_test_files returns a non-empty list for this repository."""
    root = _repo_root()
    files = _discover_test_files(root)
    assert len(files) > 0
    assert all(f.startswith("test_") and f.endswith(".py") for f in files)


# ---------------------------------------------------------------------------
# extract_main_content_by_structure tests
# ---------------------------------------------------------------------------

def _soup(html: str):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "html.parser")


def test_extract_main_content_prefers_article():
    """Should return <article> text before trying generic divs."""
    html = """
    <html><body>
      <nav><a href="/">Home</a></nav>
      <article>
        <p>Chapter one begins here.</p>
        <p>The hero walked into the forest.</p>
        <p>Birds sang softly overhead.</p>
      </article>
      <footer>Copyright 2024</footer>
    </body></html>
    """
    result = extract_main_content_by_structure(_soup(html))
    assert result is not None
    assert "hero walked" in result
    assert "Copyright" not in result


def test_extract_main_content_prefers_main():
    """Should return <main> text when present."""
    html = """
    <html><body>
      <header><nav>Menu</nav></header>
      <main>
        <p>Story paragraph one.</p>
        <p>Story paragraph two.</p>
        <p>Story paragraph three.</p>
      </main>
      <aside>Ads here</aside>
    </body></html>
    """
    result = extract_main_content_by_structure(_soup(html))
    assert result is not None
    assert "Story paragraph" in result
    assert "Ads" not in result


def test_extract_main_content_falls_back_to_dense_div():
    """When no <article>/<main>, should pick the densest <div>."""
    paragraphs = "".join(
        f"<p>Paragraph {i} of the chapter content with more words to add length.</p>"
        for i in range(10)
    )
    html = f"""
    <html><body>
      <div class="sidebar"><p>Short ad.</p></div>
      <div id="chapter-content">{paragraphs}</div>
    </body></html>
    """
    result = extract_main_content_by_structure(_soup(html))
    assert result is not None
    assert "Paragraph 0" in result


def test_extract_main_content_strips_nav_elements():
    """Nav, header, footer elements should not appear in extracted content."""
    paragraphs = "".join(
        f"<p>Story text sentence {i}.</p>" for i in range(8)
    )
    html = f"""
    <html><body>
      <nav>Nav Link 1 | Nav Link 2 | Nav Link 3</nav>
      <main>{paragraphs}</main>
      <footer>Footer content</footer>
    </body></html>
    """
    result = extract_main_content_by_structure(_soup(html))
    assert result is not None
    assert "Nav Link" not in result
    assert "Footer content" not in result


def test_extract_main_content_returns_none_for_empty():
    """Returns None (not empty string) for an empty document."""
    result = extract_main_content_by_structure(_soup("<html><body></body></html>"))
    assert result is None


def test_extract_main_content_ignores_noise_class_names():
    """Divs with ad/nav class names should be excluded."""
    real_paragraphs = "".join(
        f"<p>Real content line {i} is important prose text.</p>" for i in range(10)
    )
    html = f"""
    <html><body>
      <div class="ads-container"><p>Buy now!</p></div>
      <div class="sidebar-widget"><p>Widget text.</p></div>
      <div id="story-body">{real_paragraphs}</div>
    </body></html>
    """
    result = extract_main_content_by_structure(_soup(html))
    assert result is not None
    assert "Real content line" in result
    assert "Buy now" not in result
