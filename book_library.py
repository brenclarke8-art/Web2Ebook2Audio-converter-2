#!/usr/bin/env python3
"""
Book library for tracking per-book chapter progress and conversion settings.

Each entry records:
  - book_id            : filesystem-safe slug (immutable after creation)
  - title / author     : display metadata
  - index_url          : TOC / chapter-list page URL
  - last_chapter_count : total chapters found on the last check
  - last_processed_chapter : 1-based index of the last successfully converted chapter
  - last_settings      : full snapshot of the Config used for the last conversion
  - last_checked       : ISO-8601 UTC timestamp of the last chapter-count check
  - last_converted     : ISO-8601 UTC timestamp of the last conversion run

The library is persisted as ``<output_dir>/library.json``.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BookLibrary:
    """Manages a persistent library of books with chapter-tracking state."""

    def __init__(self, output_dir: str):
        self._path = Path(output_dir) / "library.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── persistence ──────────────────────────────────────────────────────────

    def _load(self) -> Dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning("Failed to read library %s: %s", self._path, exc)
            return {}

    def _save(self, data: Dict[str, Any]) -> None:
        try:
            self._path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Failed to save library %s: %s", self._path, exc)

    # ── book-ID helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _make_book_id(title: str) -> str:
        """Return a filesystem-safe slug derived from *title*."""
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", (title or "").strip())
        slug = slug.strip("._") or "book"
        return slug

    def _unique_book_id(self, title: str, existing: Dict[str, Any]) -> str:
        base = self._make_book_id(title)
        if base not in existing:
            return base
        counter = 2
        while f"{base}_{counter}" in existing:
            counter += 1
        return f"{base}_{counter}"

    # ── public API ────────────────────────────────────────────────────────────

    def add_book(
        self,
        title: str,
        author: str,
        index_url: str,
        settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add a new book to the library and return its *book_id*."""
        data = self._load()
        book_id = self._unique_book_id(title, data)
        data[book_id] = {
            "book_id": book_id,
            "title": title,
            "author": author,
            "index_url": index_url,
            "last_chapter_count": 0,
            "last_processed_chapter": 0,
            "last_settings": settings or {},
            "last_checked": None,
            "last_converted": None,
        }
        self._save(data)
        logger.info("Added book %r to library", book_id)
        return book_id

    def remove_book(self, book_id: str) -> bool:
        """Remove a book from the library. Returns True if it existed."""
        data = self._load()
        if book_id not in data:
            return False
        del data[book_id]
        self._save(data)
        logger.info("Removed book %r from library", book_id)
        return True

    def update_book(
        self,
        book_id: str,
        title: Optional[str] = None,
        author: Optional[str] = None,
        index_url: Optional[str] = None,
    ) -> str:
        """Edit the metadata of an existing book entry.

        Only the fields that are not ``None`` are updated.
        The *book_id* is immutable once assigned.
        Raises ``KeyError`` if *book_id* is not in the library.
        """
        data = self._load()
        if book_id not in data:
            raise KeyError(book_id)
        if title is not None:
            data[book_id]["title"] = title
        if author is not None:
            data[book_id]["author"] = author
        if index_url is not None:
            data[book_id]["index_url"] = index_url
        self._save(data)
        return book_id

    def update_after_run(
        self,
        book_id: str,
        last_processed_chapter: int,
        last_chapter_count: int,
        settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update conversion progress and settings after a successful run."""
        data = self._load()
        if book_id not in data:
            logger.warning("update_after_run: book %r not in library", book_id)
            return
        entry = data[book_id]
        entry["last_processed_chapter"] = last_processed_chapter
        entry["last_chapter_count"] = last_chapter_count
        now = datetime.now(timezone.utc).isoformat()
        entry["last_converted"] = now
        entry["last_checked"] = now
        if settings is not None:
            entry["last_settings"] = settings
        self._save(data)

    def update_checked(self, book_id: str, last_chapter_count: int) -> None:
        """Update the chapter count and last-checked timestamp after a check."""
        data = self._load()
        if book_id not in data:
            return
        data[book_id]["last_chapter_count"] = last_chapter_count
        data[book_id]["last_checked"] = datetime.now(timezone.utc).isoformat()
        self._save(data)

    def list_books(self) -> List[Dict[str, Any]]:
        """Return all book entries as a list (insertion order)."""
        return list(self._load().values())

    def get_book(self, book_id: str) -> Optional[Dict[str, Any]]:
        """Return the entry for *book_id*, or ``None`` if not found."""
        return self._load().get(book_id)


# ── Filler / unreleased chapter detection ────────────────────────────────────

class FillerChapterFilter:
    """Detect and remove placeholder chapters for unreleased or locked content.

    Sites often add stub entries to their chapter list for chapters that are
    not yet written, locked behind a paywall, or only available to subscribers.
    These should not be scraped or converted.

    Detection works at two levels:

    1. **URL-level** (cheap, before any scraping):
       The chapter URL is matched against a set of known patterns that indicate
       locked / coming-soon / premium content.

    2. **Content-level** (after scraping):
       The scraped chapter text is checked for:
       - A word count below ``min_words`` (default: 80).
       - The presence of well-known filler/paywall phrases.
       - A chapter title that itself signals placeholder content.
    """

    # Patterns matched against the URL path (case-insensitive).
    # A URL is flagged only when one of these appears as a path *component*
    # (i.e., between slashes), reducing false positives on domain names.
    _URL_PATH_PATTERNS = [
        re.compile(r'coming[_-]?soon', re.IGNORECASE),
        re.compile(r'\blocked[_-]?chapter\b', re.IGNORECASE),
        re.compile(r'\badvance[_-]?chapter\b', re.IGNORECASE),
        re.compile(r'\bpremium[_-]?chapter\b', re.IGNORECASE),
        re.compile(r'\bpaywalled?\b', re.IGNORECASE),
    ]

    # Phrases checked against the *lowercase* chapter body text.
    # Short sentences are used so minor site variations still match.
    _CONTENT_PHRASES = [
        "this chapter hasn't been released",
        "this chapter has not been released",
        "this chapter is coming soon",
        "chapter coming soon",
        "chapter is not yet available",
        "chapter not yet released",
        "chapter will be released",
        "this is a locked chapter",
        "chapter is locked",
        "unlock this chapter",
        "this chapter is premium",
        "premium chapter",
        "subscribe to read",
        "become a patron to read",
        "join our patreon to read",
        "support on patreon to access",
        "advance chapter",
        "this content is available to subscribers",
        "content not available",
        "page not found",
        "404 not found",
        "access denied",
        "you do not have permission",
    ]

    # Title keywords that flag placeholder chapters (case-insensitive).
    _TITLE_KEYWORDS = [
        "coming soon",
        "locked",
        "premium",
        "advance chapter",
        "not yet released",
        "unreleased",
    ]

    def __init__(self, min_words: int = 80):
        self.min_words = min_words

    # ── public helpers ────────────────────────────────────────────────────────

    def is_filler_url(self, url: str) -> bool:
        """Return True when *url* matches a known filler/locked pattern."""
        try:
            from urllib.parse import urlparse
            path = urlparse(url).path
        except Exception:
            path = url
        return any(pat.search(path) for pat in self._URL_PATH_PATTERNS)

    def is_filler_content(self, content: str, title: str = "") -> bool:
        """Return True when the scraped *content* (and optional *title*) looks
        like a filler / paywall placeholder."""
        # Title keyword check
        title_lc = (title or "").lower()
        if any(kw in title_lc for kw in self._TITLE_KEYWORDS):
            return True

        # Word count check
        word_count = len(content.split())
        if word_count < self.min_words:
            return True

        # Phrase check on first 1000 characters (fast, covers preamble)
        content_lc = content[:1000].lower()
        return any(phrase in content_lc for phrase in self._CONTENT_PHRASES)

    def filter_urls(
        self, urls: List[str]
    ) -> Tuple[List[str], List[str]]:
        """Split *urls* into ``(clean, filler)`` based on URL-pattern matching."""
        clean: List[str] = []
        filler: List[str] = []
        for url in urls:
            (filler if self.is_filler_url(url) else clean).append(url)
        return clean, filler

    def filter_chapters(
        self, chapters: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Split scraped *chapters* into ``(clean, filler)`` using content checks."""
        clean: List[Dict[str, Any]] = []
        filler: List[Dict[str, Any]] = []
        for ch in chapters:
            content = ch.get("content", "")
            title = ch.get("title", "")
            if self.is_filler_content(content, title):
                filler.append(ch)
            else:
                clean.append(ch)
        return clean, filler
