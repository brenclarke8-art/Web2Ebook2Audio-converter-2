from PySide6.QtCore import QObject, Signal, QThread

import logging

from ebook_app.models.scraper import WebScraper

logger = logging.getLogger(__name__)


class ScrapeThread(QThread):
    progress = Signal(str)
    index_ready = Signal(list)
    chapters_ready = Signal(list)
    error = Signal(str)

    def __init__(self, mode, url=None, chapter_urls=None):
        super().__init__()
        self.mode = mode
        self.url = url
        self.chapter_urls = chapter_urls
        self.scraper = WebScraper()
        logger.debug("Initialized ScrapeThread mode=%s url=%r chapters=%d", mode, url, len(chapter_urls or []))

    def run(self):
        try:
            logger.debug("ScrapeThread starting mode=%s", self.mode)
            if self.mode == "index":
                self.progress.emit("Scraping index...")
                urls = self.scraper.scrape_index_page(self.url)
                self.index_ready.emit(urls)
                logger.debug("ScrapeThread index mode complete urls=%d", len(urls))

            elif self.mode == "chapters":
                self.progress.emit("Scraping chapters...")
                chapters = self.scraper.scrape_chapters(self.chapter_urls)
                self.chapters_ready.emit(chapters)
                logger.debug("ScrapeThread chapter mode complete chapters=%d", len(chapters))
            else:
                logger.warning("Unsupported scrape mode: %s", self.mode)

        except Exception as e:
            logger.exception("ScrapeThread failed in mode=%s", self.mode)
            self.error.emit(str(e))


class ScrapingService(QObject):
    progress_changed = Signal(str)
    index_ready = Signal(list)
    chapters_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self._thread = None

    def _connect(self, thread):
        thread.progress.connect(self.progress_changed)
        thread.index_ready.connect(self.index_ready)
        thread.chapters_ready.connect(self.chapters_ready)
        thread.error.connect(self.error_occurred)
        thread.finished.connect(thread.deleteLater)

    def scrape_index(self, url: str):
        logger.debug("ScrapingService scrape_index requested url=%s", url)
        thread = ScrapeThread("index", url=url)
        self._thread = thread
        self._connect(thread)
        thread.start()

    def scrape_chapters(self, urls: list):
        logger.debug("ScrapingService scrape_chapters requested count=%d", len(urls or []))
        thread = ScrapeThread("chapters", chapter_urls=urls)
        self._thread = thread
        self._connect(thread)
        thread.start()
