# src/ebook_app/services/scraping_service.py
"""Threaded scraping service."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class ScrapingService(QThread):
    """QThread-based service for scraping web novels.

    Signals:
        progress (int): Emitted with values 0–100 as chapters are downloaded.
        success (list[str]): Emitted with a list of saved chapter file paths on completion.
        error (str): Emitted with an error message if scraping fails.
    """

    progress: Signal = Signal(int)
    success: Signal = Signal(list)
    error: Signal = Signal(str)

    def __init__(self, index_url: str, output_dir: str, delay_ms: int = 500) -> None:
        super().__init__()
        self.index_url = index_url
        self.output_dir = output_dir
        self.delay_ms = delay_ms

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Scrape the chapter index and download all chapters.

        TODO: implement real HTTP scraping using requests + BeautifulSoup.
        """
        try:
            # Placeholder: emit 100% immediately until logic is implemented.
            self.progress.emit(0)
            chapter_paths: list[str] = self._scrape_index()
            self.progress.emit(50)
            downloaded = self._scrape_chapters(chapter_paths)
            self.progress.emit(100)
            self.success.emit(downloaded)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))

    # ------------------------------------------------------------------
    # Placeholder methods — replace with real scraping logic
    # ------------------------------------------------------------------

    def _scrape_index(self) -> list[str]:
        """Return a list of chapter URLs from the index page.

        TODO: fetch self.index_url and parse chapter hrefs.
        """
        return []

    def _scrape_chapters(self, urls: list[str]) -> list[str]:
        """Download each chapter URL and save to self.output_dir.

        TODO: iterate *urls*, fetch each page, extract text, save as .txt.
        """
        return []
