from PySide6.QtCore import QObject, Signal, QThread

from ebook_app.models.scraping import WebScraper


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

    def run(self):
        try:
            if self.mode == "index":
                self.progress.emit("Scraping index...")
                urls = self.scraper.scrape_index_page(self.url)
                self.index_ready.emit(urls)

            elif self.mode == "chapters":
                self.progress.emit("Scraping chapters...")
                chapters = self.scraper.scrape_chapters(self.chapter_urls)
                self.chapters_ready.emit(chapters)

        except Exception as e:
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
        thread = ScrapeThread("index", url=url)
        self._thread = thread
        self._connect(thread)
        thread.start()

    def scrape_chapters(self, urls: list):
        thread = ScrapeThread("chapters", chapter_urls=urls)
        self._thread = thread
        self._connect(thread)
        thread.start()

self.scraper = ScrapingService()
self.translator = TranslationService()
self.tts = TTSService(settings)
self.epub = EPUBService(settings)
