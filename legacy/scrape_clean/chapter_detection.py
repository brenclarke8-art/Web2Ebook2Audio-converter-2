# ebook_app/pipeline/chapter_iterator.py
"""Multi-chapter iteration support.

ChapterIterator accepts a list of chapters identified from a web index,
a local folder, or an EPUB spine.  The caller sets a 1-based inclusive
range (start, end) and the iterator drives the full pipeline for each
selected chapter in sequence.

Mode-based inter-chapter flow
──────────────────────────────
  manual / semi_auto → calls ``confirm_callback(chapter_num)`` after each
                        chapter.  The callback blocks until the user clicks
                        "Start Next Chapter" or "Cancel" and returns a bool.
  auto              → the callback is not called; iteration continues
                        automatically.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# Chapter number embedded in a filename.
_CHAPTER_NUM_RE = re.compile(r"(?:chapter|ch|ep|part)[_\-\s]*(\d+)", re.IGNORECASE)
_LEADING_NUM_RE = re.compile(r"^(\d+)")
_TRAILING_NUM_RE = re.compile(r"(\d+)\.[^.]+$")


@dataclass
class ChapterInfo:
    """Metadata for a single chapter."""

    number: int
    """1-based chapter number within the full book index."""

    title: str = ""
    """Human-readable title (may be empty for scraped sources)."""

    source: str = ""
    """URL, file path, or spine ID depending on source_type."""

    source_type: str = "url"
    """One of ``'url'``, ``'file'``, ``'epub_spine'``."""


class ChapterIterator:
    """Manages chapter selection and sequential processing.

    Parameters
    ----------
    chapters:
        Full ordered list of all chapters discovered from the index.
    start:
        1-based index of the first chapter to process (inclusive).
    end:
        1-based index of the last chapter to process (inclusive).
        Pass ``0`` to process through the last available chapter.
    """

    def __init__(
        self,
        chapters: List[ChapterInfo],
        start: int = 1,
        end: int = 0,
    ) -> None:
        self._all_chapters: List[ChapterInfo] = list(chapters)
        self._cancelled: bool = False
        self.set_range(start, end)

    # ─────────────────────────────────────────────────────────────────────
    # Range management
    # ─────────────────────────────────────────────────────────────────────

    def set_range(self, start: int, end: int) -> None:
        """Set the inclusive 1-based chapter range to process.

        ``start`` and ``end`` refer to chapter *numbers* (as assigned during
        construction).  When ``end`` is 0 it means "no upper bound" — all
        chapters with number >= start are selected.
        """
        start = max(1, int(start))
        end_val = int(end)
        self._start = start
        self._end = end_val  # 0 means unbounded

        if end_val <= 0:
            self.selected_chapters: List[ChapterInfo] = [
                ch for ch in self._all_chapters if ch.number >= self._start
            ]
        else:
            self.selected_chapters = [
                ch for ch in self._all_chapters
                if self._start <= ch.number <= end_val
            ]

    @property
    def total_chapters(self) -> int:
        """Total chapters in the full index (not just selected)."""
        return len(self._all_chapters)

    @property
    def selected_count(self) -> int:
        """Number of chapters selected by the current range."""
        return len(self.selected_chapters)

    # ─────────────────────────────────────────────────────────────────────
    # Cancellation
    # ─────────────────────────────────────────────────────────────────────

    def cancel(self) -> None:
        """Request cancellation of the current iteration loop."""
        logger.debug("ChapterIterator: cancel requested.")
        self._cancelled = True

    def reset(self) -> None:
        """Clear cancellation flag."""
        self._cancelled = False

    def is_cancelled(self) -> bool:
        return self._cancelled

    # ─────────────────────────────────────────────────────────────────────
    # Source detection helpers (class methods)
    # ─────────────────────────────────────────────────────────────────────

    @classmethod
    def from_urls(cls, urls: List[str], start: int = 1, end: int = 0) -> "ChapterIterator":
        """Build a ChapterIterator from a list of scraped chapter URLs."""
        chapters = [
            ChapterInfo(number=i + 1, source=url, source_type="url")
            for i, url in enumerate(urls)
        ]
        return cls(chapters, start=start, end=end)

    @classmethod
    def from_folder(
        cls,
        folder: Path,
        extensions: tuple[str, ...] = (".txt", ".html", ".htm"),
        start: int = 1,
        end: int = 0,
    ) -> "ChapterIterator":
        """Build a ChapterIterator by scanning *folder* for chapter files.

        Chapter numbers are extracted from filenames using these strategies
        (first match wins):
          1. ``chapter_03`` / ``ch03`` / ``ep01`` embedded pattern
          2. Leading digits  (``001_title.txt``)
          3. Trailing digits before extension  (``title_07.txt``)
          4. Alphabetical sort position (fallback)
        """
        files = sorted(
            [f for f in folder.iterdir() if f.suffix.lower() in extensions],
            key=lambda f: f.name,
        )
        chapters: List[ChapterInfo] = []
        for pos, f in enumerate(files):
            stem = f.stem
            num = None

            m = _CHAPTER_NUM_RE.search(stem)
            if m:
                num = int(m.group(1))
            if num is None:
                m = _LEADING_NUM_RE.match(stem)
                if m:
                    num = int(m.group(1))
            if num is None:
                m = _TRAILING_NUM_RE.search(f.name)
                if m:
                    num = int(m.group(1))
            if num is None:
                num = pos + 1

            chapters.append(
                ChapterInfo(
                    number=num,
                    title=stem,
                    source=str(f),
                    source_type="file",
                )
            )

        # Re-number by sorted order if numbers are not unique or sequential
        numbers = [ch.number for ch in chapters]
        if len(numbers) != len(set(numbers)):
            for i, ch in enumerate(chapters):
                ch.number = i + 1

        return cls(chapters, start=start, end=end)

    @classmethod
    def from_epub_spine(
        cls,
        spine_items: List[dict],
        start: int = 1,
        end: int = 0,
    ) -> "ChapterIterator":
        """Build a ChapterIterator from an EPUB spine item list.

        Each *spine_item* dict is expected to have ``id``, ``title`` and
        optionally ``href`` keys (as produced by ebooklib).
        """
        chapters = [
            ChapterInfo(
                number=i + 1,
                title=item.get("title", f"Chapter {i + 1}"),
                source=item.get("href", item.get("id", "")),
                source_type="epub_spine",
            )
            for i, item in enumerate(spine_items)
        ]
        return cls(chapters, start=start, end=end)

    # ─────────────────────────────────────────────────────────────────────
    # Iteration
    # ─────────────────────────────────────────────────────────────────────

    def run_all(
        self,
        *,
        process_chapter: Callable[[ChapterInfo, int, int], bool],
        confirm_next: Optional[Callable[[int, int], bool]] = None,
        mode: str = "manual",
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """Iterate over selected chapters and invoke *process_chapter* for each.

        Parameters
        ----------
        process_chapter:
            ``(chapter, current_index, total) -> bool``
            Called for each chapter. Must return ``True`` on success, ``False``
            on failure (skips ``confirm_next`` for that chapter).
        confirm_next:
            ``(chapter_num, next_chapter_num) -> bool``
            Called after a chapter completes in manual/semi_auto mode.
            Should block until the user decides. Returns ``True`` to continue,
            ``False`` to cancel.
        mode:
            ``"manual"``, ``"semi_auto"``, or ``"auto"``.
        on_progress:
            ``(current_index, total)`` progress callback.

        Returns
        -------
        bool
            ``True`` if all selected chapters processed successfully,
            ``False`` if cancelled or an error occurred.
        """
        self._cancelled = False
        total = len(self.selected_chapters)
        auto = mode == "auto"

        for idx, chapter in enumerate(self.selected_chapters):
            if self._cancelled:
                logger.info("ChapterIterator: cancelled before chapter %d.", chapter.number)
                return False

            if on_progress:
                try:
                    on_progress(idx + 1, total)
                except Exception:
                    pass

            logger.info(
                "ChapterIterator: processing chapter %d (%d/%d).",
                chapter.number,
                idx + 1,
                total,
            )

            success = process_chapter(chapter, idx + 1, total)
            if not success:
                logger.warning(
                    "ChapterIterator: chapter %d processing returned failure.", chapter.number
                )
                return False

            if self._cancelled:
                return False

            # Between-chapter gate
            is_last = idx == total - 1
            if not is_last and not auto and confirm_next is not None:
                next_chapter = self.selected_chapters[idx + 1]
                try:
                    proceed = confirm_next(chapter.number, next_chapter.number)
                except Exception:
                    logger.debug("confirm_next callback raised.", exc_info=True)
                    proceed = False
                if not proceed:
                    logger.info(
                        "ChapterIterator: user declined to start chapter %d.",
                        next_chapter.number,
                    )
                    return False

        logger.info("ChapterIterator: all %d chapter(s) processed.", total)
        return True
