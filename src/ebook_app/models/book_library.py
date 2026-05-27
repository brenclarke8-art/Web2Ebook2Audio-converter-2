"""
ebook_app.models.book_library

Manages the persistent library of books, including:
- metadata (title, author, index URL)
- chapter tracking (last processed, last known count)
- timestamps for checks and conversions
- last-used conversion settings

The library is stored as JSON at:
    <output_dir>/library.json
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BookLibrary:
    """
    Persistent storage for book metadata and chapter progress.

    Parameters
    ----------
    output_dir : str | Path
        Directory where `library.json` will be stored.
    """

    def __init__(self, output_dir: str | Path):
        self._path = Path(output_dir) / "library.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------------
    # Persistence
    # ----------------------------------------------------------------------

    def _load(self) -> Dict[str, Any]:
        """Load the library JSON file, returning an empty dict if missing."""
        if not self._path.exists():
            return {}

        try:
            text = self._path.read_text(encoding="utf-8")
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning("Failed to read library %s: %s", self._path, exc)
            return {}

    def _save(self, data: Dict[str, Any]) -> None:
        """Write the library JSON file safely."""
        try:
            self._path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Failed to save library %s: %s", self._path, exc)

    # ----------------------------------------------------------------------
    # Book ID helpers
    # ----------------------------------------------------------------------

    @staticmethod
    def _make_book_id(title: str) -> str:
        """Return a filesystem-safe slug derived from the title."""
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", (title or "").strip())
        slug = slug.strip("._") or "book"
        return slug

    def _unique_book_id(self, title: str, existing: Dict[str, Any]) -> str:
        """Ensure the generated book ID does not collide with existing entries."""
        base = self._make_book_id(title)
        if base not in existing:
            return base

        counter = 2
        while f"{base}_{counter}" in existing:
            counter += 1
        return f"{base}_{counter}"

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------

    def add_book(
        self,
        title: str,
        author: str,
        index_url: str,
        settings: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add a new book entry and return its unique book_id."""
        data = self._load()
        book_id = self._unique_book_id(title, data)

        data[book_id] = {
            "book_id": book_id,
            "title": title,
            "author": author,
            "index_url": index_url,
            "raw_chapter_count": 0,
            "valid_chapter_count": 0,
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
        """Update metadata fields for an existing book."""
        data = self._load()
        if book_id not in data:
            raise KeyError(book_id)

        entry = data[book_id]
        if title is not None:
            entry["title"] = title
        if author is not None:
            entry["author"] = author
        if index_url is not None:
            entry["index_url"] = index_url

        self._save(data)
        return book_id

    def update_after_run(
        self,
        book_id: str,
        last_processed_chapter: int,
        last_chapter_count: int,
        settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update progress and settings after a conversion run."""
        data = self._load()
        if book_id not in data:
            logger.warning("update_after_run: book %r not in library", book_id)
            return

        entry = data[book_id]
        now = datetime.now(timezone.utc).isoformat()

        entry["last_processed_chapter"] = last_processed_chapter
        entry["last_chapter_count"] = last_chapter_count
        entry["last_checked"] = now
        entry["last_converted"] = now

        if settings is not None:
            entry["last_settings"] = settings

        self._save(data)

    def update_checked(self, book_id: str, last_chapter_count: int) -> None:
        """Update chapter count after a check."""
        data = self._load()
        if book_id not in data:
            return

        entry = data[book_id]
        entry["last_chapter_count"] = last_chapter_count
        entry["valid_chapter_count"] = last_chapter_count
        entry["last_checked"] = datetime.now(timezone.utc).isoformat()

        self._save(data)

    def update_inventory(self, book_id: str, raw_chapter_count: int, valid_chapter_count: int) -> None:
        """Persist chapter inventory data after scraping the index."""
        data = self._load()
        if book_id not in data:
            return

        entry = data[book_id]
        now = datetime.now(timezone.utc).isoformat()
        entry["raw_chapter_count"] = max(0, int(raw_chapter_count))
        entry["valid_chapter_count"] = max(0, int(valid_chapter_count))
        entry["last_chapter_count"] = entry["valid_chapter_count"]
        entry["last_checked"] = now
        self._save(data)

    def update_last_processed(self, book_id: str, last_processed_chapter: int) -> None:
        """Persist the latest processed chapter number for a book."""
        data = self._load()
        if book_id not in data:
            return

        entry = data[book_id]
        entry["last_processed_chapter"] = max(0, int(last_processed_chapter))
        entry["last_converted"] = datetime.now(timezone.utc).isoformat()
        self._save(data)

    def list_books(self) -> List[Dict[str, Any]]:
        """Return all book entries in insertion order."""
        return list(self._load().values())

    def get_book(self, book_id: str) -> Optional[Dict[str, Any]]:
        """Return a single book entry or None."""
        return self._load().get(book_id)


# ----------------------------------------------------------------------
# Filler chapter detection (unchanged, just relocated)
# ----------------------------------------------------------------------

class FillerChapterFilter:
    """Detect and remove placeholder chapters for unreleased or locked content."""

    _URL_PATH_PATTERNS = [
        re.compile(r'coming[_-]?soon', re.IGNORECASE),
        re.compile(r'\blocked[_-]?chapter\b', re.IGNORECASE),
        re.compile(r'\badvance[_-]?chapter\b', re.IGNORECASE),
        re.compile(r'\bpremium[_-]?chapter\b', re.IGNORECASE),
        re.compile(r'\bpaywalled?\b', re.IGNORECASE),
    ]

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

    def is_filler_url(self, url: str) -> bool:
        """Return True when the URL matches known filler patterns."""
        try:
            from urllib.parse import urlparse
            path = urlparse(url).path
        except Exception:
            path = url
        return any(pat.search(path) for pat in self._URL_PATH_PATTERNS)

    def is_filler_content(self, content: str, title: str = "") -> bool:
        """Return True when the content/title looks like a placeholder."""
        title_lc = (title or "").lower()
        if any(kw in title_lc for kw in self._TITLE_KEYWORDS):
            return True

        if len(content.split()) < self.min_words:
            return True

        content_lc = content[:1000].lower()
        return any(phrase in content_lc for phrase in self._CONTENT_PHRASES)

    def filter_urls(self, urls: List[str]) -> Tuple[List[str], List[str]]:
        """Split URLs into (clean, filler)."""
        clean, filler = [], []
        for url in urls:
            (filler if self.is_filler_url(url) else clean).append(url)
        return clean, filler

    def filter_chapters(
        self, chapters: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Split chapters into (clean, filler) based on content."""
        clean, filler = [], []
        for ch in chapters:
            if self.is_filler_content(ch.get("content", ""), ch.get("title", "")):
                filler.append(ch)
            else:
                clean.append(ch)
        return clean, filler