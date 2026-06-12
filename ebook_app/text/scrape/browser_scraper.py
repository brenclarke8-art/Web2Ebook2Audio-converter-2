# ebook_app/text/scrape/browser_scraper.py
from __future__ import annotations
import logging
import re
import time
from typing import List, Dict, Optional, Callable

from urllib.parse import urlparse, urlunparse, urljoin

from .base_scraper import BaseScraper
from .errors import ScraperError
from ebook_app.text.parse.html_cleaner import TextCleaner, extract_main_content_by_structure

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
                    if "noveldex.io" in urlparse(url).netloc:
                        content = self._extract_content_noveldex(soup)

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

    def _extract_content_noveldex(self, soup) -> str:
        """
        Extract chapter content from noveldex.io pages.

        noveldex.io scrambles paragraph order in the DOM and uses the CSS
        ``order`` flexbox property (e.g. ``style="...order: 1;..."``) to set
        the correct visual reading sequence.  This method collects every
        text-bearing leaf element together with its ``order`` value, sorts
        them in ascending order, and returns the reconstructed text.
        """
        logger.debug("Using noveldex.io CSS-order-based extraction")

        container = soup.find('body') or soup
        logger.debug("noveldex: using <body> as content container")

        ordered_elements = []

        def collect(elem, inherited_order: int = 0, has_explicit_order: bool = False) -> None:
            """Walk the subtree; inherit parent order when child has none.

            Only leaf elements that sit within an explicitly-ordered subtree
            (i.e. the element itself or an ancestor has an inline ``order:``
            CSS property) are collected.  This prevents navigation text,
            chapter titles rendered outside the flex-ordered content area, and
            other site chrome from polluting the extracted chapter text.
            """
            if not hasattr(elem, 'name') or elem.name is None:
                return
            if elem.name in ['script', 'style', 'nav', 'footer', 'header', 'noscript']:
                return

            # Parse inline 'order' value if present
            style = elem.get('style', '') or ''
            order_val = inherited_order
            explicit_here = False
            m = re.search(r'\border\s*:\s*(-?\d+)', style)
            if m:
                try:
                    order_val = int(m.group(1))
                    explicit_here = True
                except ValueError:
                    pass

            is_in_ordered_subtree = has_explicit_order or explicit_here

            # Leaf element: collect its text only when inside an ordered subtree
            has_tag_children = any(
                hasattr(child, 'name') and child.name for child in elem.children
            )
            if not has_tag_children:
                text = elem.get_text(strip=True)
                if text and is_in_ordered_subtree:
                    ordered_elements.append({'order': order_val, 'text': text, 'tag': elem.name})
            else:
                for child in elem.children:
                    collect(child, order_val, is_in_ordered_subtree)

        collect(container)
        logger.debug(f"noveldex: collected {len(ordered_elements)} leaf elements (explicitly ordered only)")

        if not ordered_elements:
            logger.debug("noveldex: no ordered elements found; falling back to regular extraction")
            return self._extract_content(soup)

        # Sort ascending by CSS order value → correct reading sequence
        ordered_elements.sort(key=lambda x: x['order'])

        texts = [item['text'] for item in ordered_elements if item['text']]
        result = '\n\n'.join(texts).strip()
        logger.debug(f"noveldex: extraction complete – {len(result)} characters")
        return result

    def _extract_content(self, soup):
        # 1. Structural / content-density heuristic (anti-scrape bypass)
        structural = extract_main_content_by_structure(soup)
        if structural:
            return structural
        # 2. Fallback: full body text
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
