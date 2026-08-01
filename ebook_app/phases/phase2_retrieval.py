# ebook_app/phases/phase2_retrieval.py
"""Phase 2 — Text Retrieval and Cleaning.

Accepts a chapter source (URL or file path) and produces clean plain text.
Web sources are scraped with WebScraper; local files are read directly
and passed through the HTML/text cleaner.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ebook_app.phases.phase_base import PhaseBase, PhaseResult

logger = logging.getLogger(__name__)


class Phase2Retrieval(PhaseBase):
    """Phase 2: retrieve and clean chapter text."""

    def run(self, chapter_id: str, **kwargs) -> PhaseResult:
        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        source: str = kwargs.get("source", "")
        source_type: str = kwargs.get("source_type", "url")
        work_dir: Any = kwargs.get("work_dir")

        if not source:
            return PhaseResult.error_result("No source provided for text retrieval.")

        self._emit_progress(5)

        try:
            raw_text, cleaned_text = self._retrieve(source, source_type, chapter_id)
        except Exception as exc:
            logger.error("[Phase2] Retrieval failed for %s: %s", chapter_id, exc, exc_info=True)
            return PhaseResult.error_result(f"Retrieval failed: {exc}")

        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        # Persist to work dir
        if work_dir:
            work_dir = Path(work_dir)
            work_dir.mkdir(parents=True, exist_ok=True)
            (work_dir / f"{chapter_id}_raw.txt").write_text(raw_text, encoding="utf-8")
            (work_dir / f"{chapter_id}_cleaned.txt").write_text(cleaned_text, encoding="utf-8")

        self._emit_progress(100)

        preview = cleaned_text[:500] + ("…" if len(cleaned_text) > 500 else "")
        return PhaseResult(
            success=True,
            output_text=cleaned_text,
            data={
                "raw_text": raw_text,
                "cleaned_text": cleaned_text,
                "preview": preview,
                "char_count": len(cleaned_text),
            },
        )

    def _retrieve(self, source: str, source_type: str, chapter_id: str) -> tuple[str, str]:
        from ebook_app.text.parse.html_cleaner import TextCleaner

        cleaner = TextCleaner()

        if source_type == "url":
            return self._scrape_url(source, cleaner)
        elif source_type == "file":
            return self._read_file(source, cleaner)
        elif source_type == "epub_spine":
            return self._read_epub_item(source, cleaner)
        else:
            raise ValueError(f"Unknown source_type: {source_type!r}")

    def _scrape_url(self, url: str, cleaner) -> tuple[str, str]:
        self._emit_progress(20)
        try:
            from ebook_app.text.scrape.browser_scraper import WebScraper
        except ImportError:
            from ebook_app.text.scrape.web_scraper import WebScraper  # type: ignore

        scraper = WebScraper()
        results = scraper.scrape_chapters([url])
        if not results:
            raise RuntimeError(f"Scraper returned no results for {url}")

        raw = results[0].get("content", "")
        self._emit_progress(70)
        cleaned = cleaner.clean(raw) if raw else ""
        return raw, cleaned

    def _read_file(self, path: str, cleaner) -> tuple[str, str]:
        self._emit_progress(20)
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
        self._emit_progress(70)
        # If HTML-like, clean it; otherwise pass through
        if "<" in raw and ">" in raw:
            cleaned = cleaner.clean(raw)
        else:
            cleaned = raw
        return raw, cleaned

    def _read_epub_item(self, spine_id: str, cleaner) -> tuple[str, str]:
        self._emit_progress(20)
        # Minimal implementation — the EPUB importer is responsible for
        # extracting individual spine items before passing them here.
        return spine_id, spine_id
