from PySide6.QtCore import QObject, Signal, QThread

import logging

from ebook_app.models.scraper import HttpWebScraper, PLAYWRIGHT_AVAILABLE

logger = logging.getLogger(__name__)

# Sentinel for when WebScraper (Playwright-based) is unavailable
try:
    from ebook_app.models.scraper import WebScraper as _WebScraper  # noqa: F401
    _BROWSER_SCRAPER_AVAILABLE = PLAYWRIGHT_AVAILABLE
except Exception:
    _BROWSER_SCRAPER_AVAILABLE = False


def _build_scraper(settings, use_browser: bool):
    """Construct the appropriate scraper from settings."""
    css_raw = (settings.get("scraper_css_selectors", "") or "").strip()
    css_selectors = [s.strip() for s in css_raw.split(",") if s.strip()] if css_raw else []
    excl_raw = (settings.get("scraper_exclude_selectors", "") or "").strip()
    exclude_selectors = [s.strip() for s in excl_raw.split(",") if s.strip()] if excl_raw else []
    max_index_pages = int(settings.get("scraper_max_index_pages", 50))
    timeout = int(settings.get("scraper_browser_timeout_sec", 30))
    delay_ms = int(settings.get("scraper_delay_ms", 500))

    if use_browser:
        if not _BROWSER_SCRAPER_AVAILABLE:
            raise ImportError(
                "Playwright is not installed. Install it with:\n"
                "  pip install playwright\n"
                "  python -m playwright install chromium\n"
                "Or switch to HTTP mode in the Scraper page."
            )
        from ebook_app.models.scraper import WebScraper
        return WebScraper(
            css_selectors=css_selectors,
            exclude_selectors=exclude_selectors,
            wait_for_js=bool(settings.get("scraper_wait_for_js", True)),
            remove_overlays=bool(settings.get("scraper_remove_overlays", True)),
            browser_timeout=timeout,
            browser_headless=not bool(settings.get("scraper_use_browser_gui", False)),
            manual_navigation=bool(settings.get("scraper_manual_navigation", False)),
            manual_navigation_timeout_sec=int(
                settings.get("scraper_manual_navigation_timeout_sec", 120)
            ),
            max_index_pages=max_index_pages,
            browser_channel=settings.get("scraper_browser_channel", "") or None,
        )

    return HttpWebScraper(
        css_selectors=css_selectors,
        exclude_selectors=exclude_selectors,
        request_delay=delay_ms / 1000.0,
        timeout=timeout,
        max_index_pages=max_index_pages,
    )


class ScrapeThread(QThread):
    progress = Signal(str)
    chapter_progress = Signal(int, int, str)   # current, total, url
    index_ready = Signal(list)
    chapters_ready = Signal(list)
    error = Signal(str)

    def __init__(self, mode, url=None, chapter_urls=None, settings=None, use_browser=False):
        super().__init__()
        self.mode = mode
        self.url = url
        self.chapter_urls = chapter_urls
        self.settings = settings
        self.use_browser = use_browser
        logger.debug(
            "Initialized ScrapeThread mode=%s url=%r chapters=%d browser=%s",
            mode, url, len(chapter_urls or []), use_browser,
        )

    def run(self):
        try:
            logger.debug("ScrapeThread starting mode=%s browser=%s", self.mode, self.use_browser)
            scraper = _build_scraper(self.settings, self.use_browser)

            if self.mode == "index":
                self.progress.emit("Scanning index pages…")
                urls = scraper.scrape_index_page(
                    self.url,
                    progress_callback=lambda msg: self.progress.emit(msg),
                )
                self.index_ready.emit(urls)
                logger.debug("ScrapeThread index complete urls=%d", len(urls))

            elif self.mode == "chapters":
                self.progress.emit(f"Scraping {len(self.chapter_urls or [])} chapters…")
                chapters = scraper.scrape_chapters(
                    self.chapter_urls,
                    progress_callback=lambda i, t, u: self.chapter_progress.emit(i, t, u),
                )
                self.chapters_ready.emit(chapters)
                logger.debug("ScrapeThread chapters complete count=%d", len(chapters))
            else:
                logger.warning("Unsupported scrape mode: %s", self.mode)

        except Exception as e:
            logger.exception("ScrapeThread failed in mode=%s", self.mode)
            self.error.emit(str(e))


class ScrapingService(QObject):
    progress_changed = Signal(str)
    chapter_progress = Signal(int, int, str)   # current, total, url
    index_ready = Signal(list)
    chapters_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, settings=None):
        super().__init__()
        self._settings = settings
        self._thread = None

    def _connect(self, thread):
        thread.progress.connect(self.progress_changed)
        thread.chapter_progress.connect(self.chapter_progress)
        thread.index_ready.connect(self.index_ready)
        thread.chapters_ready.connect(self.chapters_ready)
        thread.error.connect(self.error_occurred)
        thread.finished.connect(thread.deleteLater)

    def scrape_index(self, url: str, use_browser: bool = False):
        logger.debug("ScrapingService scrape_index url=%s browser=%s", url, use_browser)
        thread = ScrapeThread(
            "index", url=url,
            settings=self._settings, use_browser=use_browser,
        )
        self._thread = thread
        self._connect(thread)
        thread.start()

    def scrape_chapters(self, urls: list, use_browser: bool = False):
        logger.debug("ScrapingService scrape_chapters count=%d browser=%s",
                     len(urls or []), use_browser)
        thread = ScrapeThread(
            "chapters", chapter_urls=urls,
            settings=self._settings, use_browser=use_browser,
        )
        self._thread = thread
        self._connect(thread)
        thread.start()

    def cancel(self):
        if self._thread and self._thread.isRunning():
            self._thread.requestInterruption()
            self._thread.quit()
            if not self._thread.wait(2000):
                self._thread.terminate()
                self._thread.wait(1000)
            self._thread = None
            logger.info("ScrapingService thread cancelled.")
