"""Tests for pipeline/chapter_iterator.py"""
from __future__ import annotations

import pytest

from ebook_app.pipeline.chapter_iterator import ChapterInfo, ChapterIterator


# ─────────────────────────────────────────────────────────────────────────────
# from_urls
# ─────────────────────────────────────────────────────────────────────────────

def test_from_urls_creates_chapter_info_list():
    urls = [
        "https://example.com/ch1",
        "https://example.com/ch2",
        "https://example.com/ch3",
    ]
    it = ChapterIterator.from_urls(urls)
    assert it.total_chapters == 3
    assert all(c.source_type == "url" for c in it.selected_chapters)
    assert it.selected_chapters[0].number == 1
    assert it.selected_chapters[2].number == 3


def test_from_urls_range_selection():
    urls = [f"https://example.com/ch{i}" for i in range(1, 11)]
    it = ChapterIterator.from_urls(urls, start=3, end=6)
    assert it.total_chapters == 10
    assert len(it.selected_chapters) == 4
    assert it.selected_chapters[0].number == 3
    assert it.selected_chapters[-1].number == 6


def test_from_urls_range_clamps_to_available():
    urls = ["https://example.com/ch1", "https://example.com/ch2"]
    it = ChapterIterator.from_urls(urls, start=1, end=100)
    assert len(it.selected_chapters) == 2


# ─────────────────────────────────────────────────────────────────────────────
# from_folder
# ─────────────────────────────────────────────────────────────────────────────

def test_from_folder_recognises_chapter_prefix(tmp_path):
    # Create files with chapter_ prefix
    for i in [1, 3, 2]:
        (tmp_path / f"chapter_{i:02d}.txt").touch()

    it = ChapterIterator.from_folder(tmp_path)
    assert it.total_chapters == 3
    nums = [c.number for c in it.selected_chapters]
    assert sorted(nums) == [1, 2, 3]


def test_from_folder_recognises_ch_prefix(tmp_path):
    for i in [10, 20, 5]:
        (tmp_path / f"ch{i:03d}.txt").touch()

    it = ChapterIterator.from_folder(tmp_path)
    nums = sorted(c.number for c in it.selected_chapters)
    assert nums == [5, 10, 20]


def test_from_folder_range_selection(tmp_path):
    for i in range(1, 11):
        (tmp_path / f"ch{i:02d}.txt").touch()

    it = ChapterIterator.from_folder(tmp_path, start=4, end=7)
    assert len(it.selected_chapters) == 4
    nums = sorted(c.number for c in it.selected_chapters)
    assert nums == [4, 5, 6, 7]


def test_from_folder_empty_dir(tmp_path):
    it = ChapterIterator.from_folder(tmp_path)
    assert it.total_chapters == 0
    assert it.selected_chapters == []


# ─────────────────────────────────────────────────────────────────────────────
# run_all callback behaviour
# ─────────────────────────────────────────────────────────────────────────────

def test_run_all_processes_all_chapters():
    urls = ["https://example.com/ch1", "https://example.com/ch2"]
    it = ChapterIterator.from_urls(urls)

    processed = []

    def fake_process(chapter: ChapterInfo, idx: int = 0, total: int = 0) -> bool:
        processed.append(chapter.number)
        return True   # success

    it.run_all(process_chapter=fake_process, mode="auto")
    assert processed == [1, 2]


def test_run_all_auto_mode_no_confirm_needed():
    urls = [f"https://example.com/ch{i}" for i in range(1, 4)]
    it = ChapterIterator.from_urls(urls)

    confirm_called = []

    def fake_process(chapter: ChapterInfo, idx: int = 0, total: int = 0) -> bool:
        return True

    def fake_confirm(current_num: int, next_num: int) -> bool:
        confirm_called.append((current_num, next_num))
        return True

    it.run_all(process_chapter=fake_process, confirm_next=fake_confirm, mode="auto")
    # In auto mode confirm callback should NOT be called
    assert confirm_called == []


def test_run_all_manual_mode_calls_confirm():
    urls = ["https://example.com/ch1", "https://example.com/ch2", "https://example.com/ch3"]
    it = ChapterIterator.from_urls(urls)

    confirm_called = []

    def fake_process(chapter: ChapterInfo, idx: int = 0, total: int = 0) -> bool:
        return True

    def fake_confirm(current_num: int, next_num: int) -> bool:
        confirm_called.append((current_num, next_num))
        return True

    it.run_all(process_chapter=fake_process, confirm_next=fake_confirm, mode="manual")
    # Confirm should be called between chapters: ch1→ch2, ch2→ch3
    assert (1, 2) in confirm_called
    assert (2, 3) in confirm_called


def test_run_all_cancel_stops_iteration():
    urls = [f"https://example.com/ch{i}" for i in range(1, 6)]
    it = ChapterIterator.from_urls(urls)

    processed = []

    def fake_process(chapter: ChapterInfo, idx: int = 0, total: int = 0) -> bool:
        processed.append(chapter.number)
        if chapter.number == 2:
            it.cancel()
        return True

    it.run_all(process_chapter=fake_process, mode="auto")
    # Should stop after chapter 2 was cancelled
    assert 3 not in processed


def test_run_all_stops_when_confirm_returns_false():
    urls = ["https://example.com/ch1", "https://example.com/ch2", "https://example.com/ch3"]
    it = ChapterIterator.from_urls(urls)

    processed = []

    def fake_process(chapter: ChapterInfo, idx: int = 0, total: int = 0) -> bool:
        processed.append(chapter.number)
        return True

    def fake_confirm(current_num: int, next_num: int) -> bool:
        # Decline after chapter 1
        return current_num < 1

    it.run_all(process_chapter=fake_process, confirm_next=fake_confirm, mode="manual")
    assert processed == [1]
