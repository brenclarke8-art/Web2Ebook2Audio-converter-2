"""
ebook_app.models.scraping

Core + browser scraping utilities for extracting chapters, metadata, and content
from supported novel websites.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Optional Playwright Support
# ----------------------------------------------------------------------

try:
    from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class ScraperError(Exception):
    """Base exception for scraper-related errors."""
    pass


class Chapter:
    """Simple container for chapter data."""

    def __init__(self, url: str, title: str, content: str):
        self.url = url
        self.title = title
        self.content = content

    def to_dict(self) -> Dict[str, str]:
        return {"url": self.url, "title": self.title, "content": self.content}


class BaseScraper:
    """
    Base class for HTTP scraping with retry logic.
    """

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def fetch(self, url: str, *, timeout: int = 20) -> str:
        logger.debug(f"Fetching URL: {url}")
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.get(
                    url,
                    headers={"User-Agent": "ebook-app/1.0"},
                    timeout=timeout,
                )
                response.raise_for_status()
                return response.text
            except Exception as exc:
                logger.warning(
                    f"Fetch attempt {attempt}/{self.max_retries} failed for {url}: {exc}"
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    raise ScraperError(f"Failed to fetch URL after retries: {url}") from exc

    @staticmethod
    def parse_html(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    @staticmethod
    def absolute_url(base: str, link: str) -> str:
        return urljoin(base, link)

    def extract_chapter_list(self, index_url: str) -> List[str]:
        raise NotImplementedError

    def extract_chapter(self, chapter_url: str) -> Chapter:
        raise NotImplementedError


class TextCleaner:
    """Utilities for cleaning obfuscated or messy text."""

    ZERO_WIDTH_CHARS = [
        "\u200B",
        "\u200C",
        "\u200D",
        "\uFEFF",
        "\u2060",
        "\u180E",
    ]

    @staticmethod
    def remove_zero_width_chars(text: str) -> str:
        for char in TextCleaner.ZERO_WIDTH_CHARS:
            text = text.replace(char, "")
        return text

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        text = re.sub(r" +", " ", text)
        text = re.sub(r"\n\n+", "\n\n", text)
        text = "\n".join(line.strip() for line in text.split("\n"))
        return text.strip()

    @staticmethod
    def clean_text(text: str) -> str:
        return TextCleaner.normalize_whitespace(
            TextCleaner.remove_zero_width_chars(text)
        )


class HttpWebScraper:
    """Lightweight scraper that uses requests + BeautifulSoup only (no Playwright).

    Works for plain-HTML sites.  Use :class:`WebScraper` instead when the target
    site requires JavaScript rendering.
    """

    def __init__(
        self,
        css_selectors: Optional[List[str]] = None,
        exclude_selectors: Optional[List[str]] = None,
        request_delay: float = 0.5,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: int = 20,
        max_index_pages: int = 50,
    ):
        self.css_selectors = css_selectors or []
        self.exclude_selectors = exclude_selectors or []
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.max_index_pages = max(1, int(max_index_pages))
        self._base = BaseScraper(max_retries=max_retries, retry_delay=retry_delay)
        self._pagination_keywords = {"next", "siguiente", "suivant", "continue",
                                     "older", "more", "page", "pages", ">>", "›", "»"}

    # ------------------------------------------------------------------
    # Public API — same shape as WebScraper so ScrapingService can use either
    # ------------------------------------------------------------------

    def scrape_index_page(
        self,
        index_url: str,
        max_pages: int = 50,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> List[str]:
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
                html = self._base.fetch(current, timeout=self.timeout)
            except Exception as exc:
                logger.warning("Failed to fetch index page %s: %s", current, exc)
                continue

            soup = BeautifulSoup(html, "html.parser")
            chapters, next_pages = self._extract_links(soup, current, base_url, host, index_path)

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

        logger.info("HTTP index scrape complete: %d chapter URLs discovered.", len(chapter_urls))
        return chapter_urls

    def scrape_chapters(
        self,
        urls: List[str],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[Dict[str, str]]:
        total = len(urls)
        results: List[Dict[str, str]] = []
        for idx, url in enumerate(urls, start=1):
            if progress_callback:
                progress_callback(idx, total, url)
            try:
                html = self._base.fetch(url, timeout=self.timeout)
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()
                for sel in self.exclude_selectors:
                    try:
                        for el in soup.select(sel):
                            el.decompose()
                    except Exception:
                        pass
                title = self._detect_title(soup)
                content = self._extract_content(soup)
                results.append({"url": url, "title": title,
                                 "content": TextCleaner.clean_text(content)})
                logger.debug("HTTP chapter %d/%d OK: %s", idx, total, url)
            except Exception as exc:
                logger.error("HTTP chapter fetch failed %s: %s", url, exc)
                results.append({"url": url, "title": "Failed to scrape", "content": "", "error": str(exc)})
            if self.request_delay > 0:
                time.sleep(self.request_delay)
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
        soup: BeautifulSoup,
        current_url: str,
        base_url: str,
        host: str,
        index_path: str,
    ) -> Tuple[List[str], List[str]]:
        chapter_urls: List[str] = []
        pagination_urls: List[str] = []
        cur_parsed = urlparse(current_url)
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
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
            is_pag = (any(k in link_text for k in self._pagination_keywords)
                      or re.search(r"[?&](page|p)=\d+", href.lower())
                      or re.search(r"/(page|p)/\d+", link_path)
                      or bool(re.fullmatch(r"\d{1,4}", link_text)))
            is_ch = "chapter" in link_path or (
                bool(re.search(r"/\d+/?$", link_path))
                and link_path.startswith(index_path)
                and link_path != index_path + "/")
            if is_pag:
                pagination_urls.append(href)
            elif is_ch:
                chapter_urls.append(href)
        return chapter_urls, pagination_urls

    def _extract_content(self, soup: BeautifulSoup) -> str:
        if self.css_selectors:
            parts = []
            for sel in self.css_selectors:
                for el in soup.select(sel):
                    parts.append(el.get_text(separator="\n", strip=True))
            if parts:
                return "\n\n".join(parts)
        body = soup.find("body") or soup
        return body.get_text(separator="\n", strip=True)

    @staticmethod
    def _detect_title(soup: BeautifulSoup) -> str:
        for tag in ["h1", "h2", "title", "h3"]:
            el = soup.find(tag)
            if el:
                t = el.get_text(strip=True)
                if t and len(t) < 200:
                    return t
        return "Chapter"


class BrowserScraper:
    """
    Headless browser scraper using Playwright.
    """

    _JS_VISUAL_ORDER_SCRIPT = """
    (params) => {
        const cssSelectors     = params.cssSelectors || [];
        const excludeSelectors = params.excludeSelectors || [];
        const skipTags = new Set(['script','style','nav','footer','header','noscript','iframe']);

        let containers = [];
        if (cssSelectors.length > 0) {
            cssSelectors.forEach(sel => {
                try { document.querySelectorAll(sel).forEach(el => containers.push(el)); } catch(e) {}
            });
        }
        if (containers.length === 0 && document.body) containers = [document.body];

        const excludedRoots = [];
        excludeSelectors.forEach(sel => {
            try { document.querySelectorAll(sel).forEach(el => excludedRoots.push(el)); } catch(e) {}
        });

        function isExcluded(el) {
            for (const root of excludedRoots) {
                if (root === el || root.contains(el)) return true;
            }
            return false;
        }

        const results = [];
        const seenNodes = new WeakSet();

        containers.forEach(container => {
            const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                if (seenNodes.has(node)) continue;
                seenNodes.add(node);

                const text = (node.nodeValue || '').trim();
                if (!text) continue;

                const parent = node.parentElement;
                if (!parent) continue;
                if (isExcluded(parent)) continue;

                const tag = parent.tagName.toLowerCase();
                if (skipTags.has(tag)) continue;

                try {
                    const style = window.getComputedStyle(parent);
                    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity || '1') < 0.01) continue;
                } catch(e) {}

                const rect = parent.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;

                results.push({
                    text: text,
                    top: Math.round(rect.top + window.scrollY),
                    left: Math.round(rect.left + window.scrollX),
                    height: Math.round(rect.height),
                    tag: tag
                });
            }
        });

        return results;
    }
    """

    def __init__(
        self,
        headless: bool = True,
        timeout_ms: int = 30000,
        wait_for_js: bool = True,
        remove_overlays: bool = True,
        manual_navigation: bool = False,
        manual_navigation_timeout_sec: int = 120,
        browser_channel: Optional[str] = None,
    ):
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not installed — BrowserScraper unavailable")
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.wait_for_js = wait_for_js
        self.remove_overlays = remove_overlays
        self.manual_navigation = manual_navigation
        self.manual_navigation_timeout_sec = max(1, int(manual_navigation_timeout_sec))
        self.browser_channel = browser_channel or None

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self.last_page_url: Optional[str] = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        logger.debug(
            "Launching browser headless=%s channel=%s timeout_ms=%d manual_navigation=%s",
            self.headless,
            self.browser_channel or "chromium-default",
            self.timeout_ms,
            self.manual_navigation,
        )
        launch_kwargs = {"headless": self.headless}
        if self.browser_channel:
            launch_kwargs["channel"] = self.browser_channel
        self._browser = self._playwright.chromium.launch(**launch_kwargs)
        self._context = self._browser.new_context()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def _remove_overlays(self, page: Page) -> None:
        overlay_script = """
        () => {
            const elements = document.querySelectorAll('*');
            elements.forEach(el => {
                const style = window.getComputedStyle(el);
                const zIndex = parseInt(style.zIndex || '0', 10);

                if (zIndex > 1000) el.remove();

                if ((style.position === 'fixed' || style.position === 'absolute') &&
                    (style.width === '100%' || style.height === '100%')) {
                    const opacity = parseFloat(style.opacity || '1');
                    if (opacity < 0.1) el.remove();
                }

                if (style.userSelect === 'none' && el.children.length === 0) {
                    el.style.userSelect = 'auto';
                }
            });

            if (document.body) {
                document.body.style.userSelect = 'auto';
                document.body.style.webkitUserSelect = 'auto';
            }
        }
        """
        try:
            page.evaluate(overlay_script)
            logger.debug("Overlay cleanup script executed for page=%s", page.url)
        except Exception as exc:
            logger.warning(f"Failed to remove overlays: {exc}")

    def _await_manual_navigation(self, page: Page, url: str) -> None:
        if not self.manual_navigation or self.headless:
            return
        logger.info(
            "Manual browser mode active for %s. Navigate/login/dismiss popups, then click the confirm button in the page to continue.",
            url,
        )
        page.bring_to_front()
        page.evaluate(
            """
            () => {
                if (typeof window.__ebookManualNavCleanup === 'function') {
                    window.__ebookManualNavCleanup();
                }
                window.__ebookManualNavConfirmed = false;
                const existing = document.getElementById('ebook-manual-nav-confirm');
                if (existing) existing.remove();
                const wrap = document.createElement('div');
                wrap.id = 'ebook-manual-nav-confirm';
                wrap.style.position = 'fixed';
                wrap.style.bottom = '16px';
                wrap.style.right = '16px';
                wrap.style.zIndex = '2147483647';
                wrap.style.background = 'rgba(17,17,17,0.92)';
                wrap.style.border = '1px solid #3a3a3a';
                wrap.style.borderRadius = '10px';
                wrap.style.padding = '12px';
                wrap.style.boxShadow = '0 4px 18px rgba(0,0,0,0.45)';

                const label = document.createElement('div');
                label.textContent = 'When ready, confirm this page for capture.';
                label.style.color = '#fff';
                label.style.fontFamily = 'system-ui, sans-serif';
                label.style.fontSize = '13px';
                label.style.marginBottom = '8px';
                wrap.appendChild(label);

                const button = document.createElement('button');
                button.type = 'button';
                button.textContent = '✅ Confirm and Continue';
                button.style.cursor = 'pointer';
                button.style.background = '#1678c2';
                button.style.border = 'none';
                button.style.color = '#fff';
                button.style.fontSize = '13px';
                button.style.fontWeight = '600';
                button.style.padding = '8px 12px';
                button.style.borderRadius = '6px';
                button.addEventListener('click', () => {
                    window.__ebookManualNavConfirmed = true;
                });
                wrap.appendChild(button);

                document.documentElement.appendChild(wrap);
                window.__ebookManualNavCleanup = () => {
                    const current = document.getElementById('ebook-manual-nav-confirm');
                    if (current) current.remove();
                };
            }
            """
        )
        try:
            page.wait_for_function("() => window.__ebookManualNavConfirmed === true", timeout=0)
            logger.info("Manual navigation confirmed; capturing current page at %s", page.url)
        finally:
            try:
                page.evaluate(
                    """
                    () => {
                        if (typeof window.__ebookManualNavCleanup === 'function') {
                            window.__ebookManualNavCleanup();
                        }
                        delete window.__ebookManualNavCleanup;
                        delete window.__ebookManualNavConfirmed;
                    }
                    """
                )
            except Exception:
                logger.debug("Manual navigation prompt cleanup skipped for %s", page.url, exc_info=True)

    def extract_visual_text(
        self,
        page: Page,
        css_selectors: Optional[List[str]] = None,
        exclude_selectors: Optional[List[str]] = None,
    ) -> List[Dict[str, Union[str, int]]]:
        params = {
            "cssSelectors": css_selectors or [],
            "excludeSelectors": exclude_selectors or [],
        }
        return page.evaluate(self._JS_VISUAL_ORDER_SCRIPT, params)

    def scrape_page(
        self,
        url: str,
        *,
        visual_order_params: Optional[Dict] = None,
        manual_navigation: Optional[bool] = None,
    ) -> Union[str, Tuple[str, List[Dict[str, Union[str, int]]]]]:
        if not self._context:
            raise RuntimeError("BrowserScraper context is not initialized")

        page = self._context.new_page()
        try:
            logger.debug("Navigating browser page to %s", url)
            page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            effective_manual_navigation = self.manual_navigation if manual_navigation is None else manual_navigation
            if effective_manual_navigation and not self.headless:
                self._await_manual_navigation(page, url)
            if self.wait_for_js:
                try:
                    page.wait_for_load_state("load", timeout=self.timeout_ms)
                    time.sleep(1)
                except Exception as exc:
                    logger.warning(f"Page load wait timeout for {url}: {exc}")

            if self.remove_overlays:
                self._remove_overlays(page)

            self.last_page_url = page.url
            logger.debug("Captured HTML from %s (requested=%s)", self.last_page_url, url)
            html = page.content()

            if visual_order_params is not None:
                nodes = self.extract_visual_text(
                    page,
                    visual_order_params.get("css_selectors"),
                    visual_order_params.get("exclude_selectors"),
                )
                return html, nodes

            return html
        finally:
            page.close()


class WebScraper:
    """
    High-level scraper that uses BrowserScraper.
    """

    _CSS_ORDER_SCALE_FACTOR = 100
    _MAX_NUMERIC_PAGE_DIGITS = 4

    def __init__(
        self,
        css_selectors: Optional[List[str]] = None,
        use_visual_order: bool = False,
        wait_for_js: bool = True,
        remove_overlays: bool = True,
        browser_timeout: int = 30,
        exclude_selectors: Optional[List[str]] = None,
        browser_headless: bool = True,
        manual_navigation: bool = False,
        manual_navigation_timeout_sec: int = 120,
        max_index_pages: int = 50,
        browser_channel: Optional[str] = None,
    ):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "Playwright not installed. Install with:\n"
                "    pip install playwright\n"
                "    python -m playwright install chromium"
            )

        self.css_selectors = css_selectors or []
        self.exclude_selectors = exclude_selectors or []
        self.use_visual_order = use_visual_order
        self.wait_for_js = wait_for_js
        self.remove_overlays = remove_overlays
        self.browser_timeout = browser_timeout
        self.browser_headless = browser_headless
        self.manual_navigation = manual_navigation
        self.manual_navigation_timeout_sec = max(1, int(manual_navigation_timeout_sec))
        self.max_index_pages = max(1, int(max_index_pages))
        self.browser_channel = browser_channel or None
        self.chapters: List[Dict[str, str]] = []
        self._pagination_keywords = {
            "next",
            "siguiente",
            "suivant",
            "continue",
            "older",
            "more",
            "page",
            "pages",
            ">>",
            "›",
            "»",
        }

        logger.debug(
            "WebScraper initialized headless=%s manual_navigation=%s timeout=%ss max_index_pages=%d selectors=%d exclude=%d",
            self.browser_headless,
            self.manual_navigation,
            self.browser_timeout,
            self.max_index_pages,
            len(self.css_selectors),
            len(self.exclude_selectors),
        )

    def scrape_chapters(
        self,
        urls: List[str],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[Dict[str, str]]:
        return self._scrape_chapters_browser(urls, progress_callback=progress_callback)

    @staticmethod
    def _canonicalize_url(url: str) -> str:
        parsed = urlparse(url)
        normalized_path = parsed.path
        if normalized_path and normalized_path != "/":
            normalized_path = normalized_path.rstrip("/")
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                normalized_path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )

    def scrape_index_page(
        self,
        index_url: str,
        max_pages: int = 50,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> List[str]:
        effective_max_pages = max_pages if max_pages > 0 else self.max_index_pages
        logger.info(
            "Scraping index pages from %s with max_pages=%d manual_navigation=%s",
            index_url,
            effective_max_pages,
            self.manual_navigation,
        )
        parsed_index = urlparse(index_url)
        base_url = f"{parsed_index.scheme}://{parsed_index.netloc}"
        host = parsed_index.netloc

        chapter_urls: List[str] = []
        seen_chapters: set[str] = set()
        seen_index_pages: set[str] = set()
        pages_to_visit = [self._canonicalize_url(index_url)]

        with BrowserScraper(
            headless=self.browser_headless,
            timeout_ms=self.browser_timeout * 1000,
            wait_for_js=self.wait_for_js,
            remove_overlays=self.remove_overlays,
            manual_navigation=self.manual_navigation,
            manual_navigation_timeout_sec=self.manual_navigation_timeout_sec,
            browser_channel=self.browser_channel,
        ) as browser:
            page_count = 0
            while pages_to_visit and page_count < effective_max_pages:
                current_page_url = self._canonicalize_url(pages_to_visit.pop(0))
                if current_page_url in seen_index_pages:
                    continue

                seen_index_pages.add(current_page_url)
                page_count += 1

                if progress_callback:
                    progress_callback(
                        f"Scanning index page {page_count}/{effective_max_pages}: {current_page_url}"
                    )
                logger.debug(
                    "Index crawl page %d/%d queued=%d url=%s",
                    page_count,
                    effective_max_pages,
                    len(pages_to_visit),
                    current_page_url,
                )
                html = browser.scrape_page(
                    current_page_url,
                    manual_navigation=self.manual_navigation and page_count == 1,
                )
                resolved_url = browser.last_page_url or current_page_url
                soup = BeautifulSoup(html, "html.parser")

                page_chapters, next_page_links = self._extract_chapter_and_pagination_links(
                    soup,
                    resolved_url,
                    base_url,
                    host,
                    parsed_index.path,
                )
                logger.debug(
                    "Parsed index page=%s found_chapters=%d next_pages=%d",
                    resolved_url,
                    len(page_chapters),
                    len(next_page_links),
                )

                for ch in page_chapters:
                    canonical_ch = self._canonicalize_url(ch)
                    if canonical_ch not in seen_chapters:
                        seen_chapters.add(canonical_ch)
                        chapter_urls.append(ch)

                for next_link in next_page_links:
                    canonical_next = self._canonicalize_url(next_link)
                    if canonical_next not in seen_index_pages and canonical_next not in pages_to_visit:
                        pages_to_visit.append(canonical_next)

        logger.info("Index scraping complete: discovered %d unique chapter URLs.", len(chapter_urls))
        return chapter_urls

    def _extract_chapter_and_pagination_links(
        self,
        soup: BeautifulSoup,
        current_url: str,
        base_url: str,
        host: str,
        index_path: str,
    ) -> Tuple[List[str], List[str]]:
        chapter_urls: List[str] = []
        pagination_urls: List[str] = []

        current_parsed = urlparse(current_url)
        index_path_clean = index_path.rstrip("/")

        logger.debug("Extracting chapter and pagination links from %s", current_url)
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            if href.startswith("//"):
                href = current_parsed.scheme + ":" + href
            elif href.startswith("/"):
                href = base_url + href
            elif not href.startswith("http"):
                href = urljoin(current_url, href)

            if urlparse(href).netloc != host:
                continue

            link_path = urlparse(href).path.lower()
            link_text = a_tag.get_text(strip=True).lower()

            numeric_page_pattern = rf"\d{{1,{self._MAX_NUMERIC_PAGE_DIGITS}}}"
            is_numeric_page_link = bool(re.fullmatch(numeric_page_pattern, link_text))
            is_pagination = (
                any(k in link_text for k in self._pagination_keywords)
                or re.search(r"[?&](page|p)=\d+", href.lower())
                or re.search(r"/(page|p)/\d+", link_path)
                or is_numeric_page_link
            )

            is_chapter_path = "chapter" in link_path
            is_deeper_numeric = (
                bool(re.search(r"/\d+/?$", link_path))
                and link_path.startswith(index_path_clean)
                and link_path != index_path_clean + "/"
            )

            if is_pagination:
                pagination_urls.append(href)
            elif is_chapter_path or is_deeper_numeric:
                chapter_urls.append(href)

        return chapter_urls, pagination_urls

    def _scrape_chapters_browser(
        self,
        urls: List[str],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[Dict[str, str]]:
        logger.info("Scraping %d chapter pages with browser.", len(urls))
        self.chapters = []
        with BrowserScraper(
            headless=self.browser_headless,
            timeout_ms=self.browser_timeout * 1000,
            wait_for_js=self.wait_for_js,
            remove_overlays=self.remove_overlays,
            manual_navigation=self.manual_navigation,
            manual_navigation_timeout_sec=self.manual_navigation_timeout_sec,
            browser_channel=self.browser_channel,
        ) as browser:
            total = len(urls)
            for idx, url in enumerate(urls, start=1):
                if progress_callback:
                    progress_callback(idx, total, url)
                try:
                    logger.debug("Scraping chapter %d/%d: %s", idx, total, url)
                    self.chapters.append(self._scrape_single_browser(url, browser))
                except Exception as exc:
                    logger.error(f"Error scraping {url}: {exc}")
                    self.chapters.append({"url": url, "title": "Failed to scrape",
                                          "content": "", "error": str(exc)})
        logger.info("Chapter scraping complete: %d successful pages.", len(self.chapters))
        return self.chapters

    def _scrape_single_browser(self, url: str, browser: BrowserScraper) -> Dict[str, str]:
        logger.debug("Extracting chapter content from %s (visual_order=%s)", url, self.use_visual_order)
        if self.use_visual_order:
            visual_params = {
                "css_selectors": self.css_selectors,
                "exclude_selectors": self.exclude_selectors,
            }
            html, visual_nodes = browser.scrape_page(url, visual_order_params=visual_params)
            soup = BeautifulSoup(html, "html.parser")
            title = self._detect_title(soup)

            if visual_nodes:
                content = self._visual_nodes_to_text(visual_nodes)
            else:
                content = self._extract_content(soup)

            return {"url": url, "title": title, "content": TextCleaner.clean_text(content)}

        html = browser.scrape_page(url)
        soup = BeautifulSoup(html, "html.parser")
        return self._process_soup(soup, url)

    @staticmethod
    def _visual_nodes_to_text(nodes: List[Dict[str, Union[str, int]]]) -> str:
        ordered = sorted(
            nodes,
            key=lambda n: (int(n.get("top", 0)), int(n.get("left", 0))),
        )
        parts: List[str] = []
        for n in ordered:
            txt = str(n.get("text", "")).strip()
            if txt:
                parts.append(txt)
        return "\n\n".join(parts).strip()

    def _process_soup(self, soup: BeautifulSoup, url: str) -> Dict[str, str]:
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        for selector in self.exclude_selectors:
            try:
                for elem in soup.select(selector):
                    elem.decompose()
            except Exception as exc:
                logger.warning(f"Exclude selector failed '{selector}': {exc}")

        if self._is_noveldex_url(url):
            content = self._extract_content_noveldex(soup)
        else:
            content = self._extract_content(soup)

        return {
            "url": url,
            "title": self._detect_title(soup),
            "content": TextCleaner.clean_text(content),
        }

    def _extract_content(self, soup: BeautifulSoup) -> str:
        content_parts: List[str] = []

        if self.css_selectors:
            for selector in self.css_selectors:
                for elem in soup.select(selector):
                    text = (
                        self._extract_text_visual_order(elem)
                        if self.use_visual_order
                        else self._extract_text_from_element(elem)
                    )
                    if text:
                        content_parts.append(text)

        if not content_parts:
            body = soup.find("body") or soup
            text = (
                self._extract_text_visual_order(body)
                if self.use_visual_order
                else self._extract_text_from_element(body)
            )
            if text:
                content_parts.append(text)

        return "\n\n".join(content_parts).strip()

    @staticmethod
    def _extract_text_from_element(element) -> str:
        return element.get_text(separator="\n", strip=True)

    def _extract_text_visual_order(self, element) -> str:
        text_elements: List[Dict[str, Union[str, int]]] = []

        def walk(elem, depth: int = 0):
            if depth > 50:
                return
            if not hasattr(elem, "name") or elem.name is None:
                return
            if elem.name in ["script", "style", "nav", "footer", "header", "noscript"]:
                return

            children = [c for c in getattr(elem, "children", []) if hasattr(c, "name")]
            if not children:
                text = elem.get_text(separator=" ", strip=True)
                if text:
                    pos = self._get_position_hint(elem)
                    text_elements.append(
                        {
                            "text": text,
                            "top": int(pos["top"]),
                            "left": int(pos["left"]),
                        }
                    )
                return

            for child in children:
                walk(child, depth + 1)

        walk(element)

        text_elements.sort(key=lambda x: (int(x["top"]), int(x["left"])))
        return "\n\n".join(str(x["text"]) for x in text_elements if x["text"]).strip()

    @staticmethod
    def _is_noveldex_url(url: str) -> bool:
        try:
            hostname = urlparse(url).hostname or ""
            return hostname == "noveldex.io" or hostname.endswith(".noveldex.io")
        except Exception:
            return False

    def _extract_content_noveldex(self, soup: BeautifulSoup) -> str:
        container = None
        for selector in self.css_selectors:
            try:
                elements = soup.select(selector)
                if elements:
                    container = elements[0]
                    break
            except Exception:
                pass

        if container is None:
            container = soup.find("body") or soup

        ordered_elements: List[Tuple[int, str]] = []

        def collect(elem, inherited_order: int = 0, in_ordered_subtree: bool = False):
            if not hasattr(elem, "name") or elem.name is None:
                return
            if elem.name in ["script", "style", "nav", "footer", "header", "noscript"]:
                return

            style = elem.get("style", "") or ""
            m = re.search(r"\border\s*:\s*(-?\d+)", style)

            if m:
                try:
                    order_val = int(m.group(1))
                    explicit_here = True
                except ValueError:
                    order_val = inherited_order
                    explicit_here = False
            else:
                order_val = inherited_order
                explicit_here = False

            subtree_ordered = in_ordered_subtree or explicit_here
            children = [c for c in getattr(elem, "children", []) if hasattr(c, "name")]

            if not children:
                text = elem.get_text(separator=" ", strip=True)
                if text and subtree_ordered:
                    ordered_elements.append((order_val, text))
                return

            for child in children:
                collect(child, order_val, subtree_ordered)

        collect(container)

        if not ordered_elements:
            return self._extract_text_from_element(container)

        ordered_elements.sort(key=lambda x: x[0])
        return "\n\n".join(text for _, text in ordered_elements).strip()

    def _get_position_hint(self, element) -> Dict[str, float]:
        top = 0.0
        left = 0.0

        style = element.get("style", "") or ""
        m = re.search(r"\border\s*:\s*(-?\d+)", style)
        if m:
            try:
                top = float(m.group(1)) * self._CSS_ORDER_SCALE_FACTOR
            except ValueError:
                pass

        if "top:" in style:
            try:
                val = style.split("top:")[1].split(";")[0].strip().replace("px", "")
                top = float(val)
            except Exception:
                pass

        if "left:" in style:
            try:
                val = style.split("left:")[1].split(";")[0].strip().replace("px", "")
                left = float(val)
            except Exception:
                pass

        classes = element.get("class", [])
        class_str = " ".join(classes) if isinstance(classes, list) else str(classes)
        lc = class_str.lower()

        if "right" in lc:
            left += 1000
        elif "left" in lc:
            left -= 1000

        if "top" in lc:
            top -= 1000
        elif "bottom" in lc:
            top += 1000

        return {"top": top, "left": left}

    @staticmethod
    def _detect_title(soup: BeautifulSoup) -> str:
        # 1) Strong semantic tags
        for tag in ["h1", "h2", "title", "h3"]:
            el = soup.find(tag)
            if el:
                title = el.get_text(strip=True)
                if title and len(title) < 200:
                    return title

        # 2) Common class names used by novel sites
        for cls in ["chapter-title", "entry-title", "post-title"]:
            el = soup.find(class_=cls)
            if el:
                title = el.get_text(strip=True)
                if title and len(title) < 200:
                    return title

        # 3) Regex fallback: "Chapter 123", "Ch. 45", etc.
        text = soup.get_text(" ", strip=True)
        m = re.search(r"(chapter|ch\.?)\s*\d{1,4}", text, re.IGNORECASE)
        if m:
            return m.group(0).strip().title()

        # 4) Final fallback
        return "Chapter"
