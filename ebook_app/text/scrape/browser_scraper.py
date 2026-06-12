# ebook_app/text/scrape/browser_scraper.py
from __future__ import annotations
import logging
import time
from typing import List, Dict, Optional, Callable

from urllib.parse import urlparse, urlunparse, urljoin

from .base_scraper import BaseScraper
from .errors import ScraperError
from ebook_app.text.parse.html_cleaner import TextCleaner

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class WebScraper:
    """
    Playwright-based scraper for JS-heavy sites.

    Contract-compliant:
      - scrape_index_page(url, max_pages)
      - scrape_chapters(urls)
    """

    def __init__(
        self,
        *,
        wait_for_js: bool = True,
        remove_overlays: bool = True,
        browser_timeout: int = 30,
        browser_headless: bool = True,
        manual_navigation: bool = False,
        manual_navigation_timeout_sec: int = 120,
        max_index_pages: int = 50,
        browser_channel: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        request_delay: float = 0.5,
    ):
        self.wait_for_js = wait_for_js
        self.remove_overlays = remove_overlays
        self.browser_timeout = browser_timeout
        self.browser_headless = browser_headless
        self.manual_navigation = manual_navigation
        self.manual_navigation_timeout_sec = manual_navigation_timeout_sec
        self.max_index_pages = max_index_pages
        self.browser_channel = browser_channel
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.request_delay = request_delay

        self._pagination_keywords = {
            "next", "siguiente", "suivant", "continue",
            "older", "more", "page", "pages", ">>", "›", "»"
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scrape_index_page(
        self,
        index_url: str,
        max_pages: int = 50,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> List[str]:

        if not PLAYWRIGHT_AVAILABLE:
            raise ScraperError("Playwright is not installed")

        effective_max = max_pages if max_pages > 0 else self.max_index_pages

        parsed = urlparse(index_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        host = parsed.netloc
        index_path = parsed.path.rstrip("/")

        chapter_urls: List[str] = []
        seen_chapters: set = set()
        seen_index: set = set()
        queue = [index_url]
        page_num = 0

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=self.browser_headless,
                channel=self.browser_channel,
            )
            page = browser.new_page()

            while queue and page_num < effective_max:
                current = queue.pop(0)
                canonical = self._canonicalize(current)
                if canonical in seen_index:
                    continue
                seen_index.add(canonical)
                page_num += 1

                if progress_callback:
                    progress_callback(f"Scraping index page {page_num}/{effective_max}: {current}")

                try:
                    page.goto(current, timeout=self.browser_timeout * 1000)

                    if self.wait_for_js:
                        page.wait_for_load_state("networkidle")

                    if self.remove_overlays:
                        self._remove_overlays(page)

                    soup_html = page.content()
                except Exception as exc:
                    logger.warning("Failed to fetch index page %s: %s", current, exc)
                    continue

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(soup_html, "html.parser")

                chapters, next_pages = self._extract_links(
                    soup, current, base_url, host, index_path
                )

                for ch in chapters:
                    c = self._canonicalize(ch)
                    if c not in seen_chapters:
                        seen_chapters.add(c)
                        chapter_urls.append(ch)

                for np in next_pages:
                    c = self._canonicalize(np)
                    if c not in seen_index:
                        queue.append(np)

                if self.request_delay > 0:
                    time.sleep(self.request_delay)

            browser.close()

        logger.info("Browser index scrape complete: %d chapter URLs discovered.", len(chapter_urls))
        return chapter_urls

    def scrape_chapters(
        self,
        urls: List[str],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[Dict[str, str]]:

        if not PLAYWRIGHT_AVAILABLE:
            raise ScraperError("Playwright is not installed")

        results: List[Dict[str, str]] = []
        total = len(urls)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=self.browser_headless,
                channel=self.browser_channel,
            )
            page = browser.new_page()

            for idx, url in enumerate(urls, start=1):
                if progress_callback:
                    progress_callback(idx, total, url)

                try:
                    page.goto(url, timeout=self.browser_timeout * 1000)

                    if self.wait_for_js:
                        page.wait_for_load_state("networkidle")

                    if self.remove_overlays:
                        self._remove_overlays(page)

                    title = page.title()
                    html = page.content()

                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, "html.parser")

                    for tag in soup(["script", "style", "nav", "footer"]):
                        tag.decompose()

                    content = self._extract_content(soup)

                    results.append({
                        "url": url,
                        "title": title or "Untitled",
                        "content": TextCleaner.clean_text(content),
                    })

                except Exception as exc:
                    logger.error("Browser chapter fetch failed %s: %s", url, exc)
                    results.append({
                        "url": url,
                        "title": "Failed to scrape",
                        "content": "",
                        "error": str(exc),
                    })

                if self.request_delay > 0:
                    time.sleep(self.request_delay)

            browser.close()

        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _canonicalize(url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/") or "/"
        return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params,
                           parsed.query, parsed.fragment))

    def _extract_links(
        self,
        soup,
        current_url: str,
        base_url: str,
        host: str,
        index_path: str,
    ):
        import re
        chapter_urls = []
        pagination_urls = []

        cur_parsed = urlparse(current_url)

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            # Normalize
            if href.startswith("//"):
                href = cur_parsed.scheme + ":" + href
            elif href.startswith("/"):
                href = base_url + href
            elif not href.startswith("http"):
                href = urljoin(current_url, href)

            if urlparse(href).netloc != host:
                continue

            link_path = urlparse(href).path.lower()
            link_text = a.get_text(strip=True).lower()

            is_pag = (
                any(k in link_text for k in self._pagination_keywords)
                or re.search(r"[?&](page|p)=\d+", href.lower())
                or re.search(r"/(page|p)/\d+", link_path)
                or bool(re.fullmatch(r"\d{1,4}", link_text))
            )

            is_ch = (
                "chapter" in link_path
                or (
                    bool(re.search(r"/\d+/?$", link_path))
                    and link_path.startswith(index_path)
                    and link_path != index_path + "/"
                )
            )

            if is_pag:
                pagination_urls.append(href)
            elif is_ch:
                chapter_urls.append(href)

        return chapter_urls, pagination_urls

    def _extract_content(self, soup):
        if soup.body:
            return soup.body.get_text(separator="\n", strip=True)
        return soup.get_text(separator="\n", strip=True)

    def _remove_overlays(self, page):
        page.evaluate(
            """
            () => {
                const selectors = ['div[style*="z-index"]', '.overlay', '.modal'];
                for (const sel of selectors) {
                    document.querySelectorAll(sel).forEach(el => el.remove());
                }
            }
            """
        )
