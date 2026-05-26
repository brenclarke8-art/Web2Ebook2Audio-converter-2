"""
ebook_app.models.scraping

Core + browser scraping utilities for extracting chapters, metadata, and content
from supported novel websites.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

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
    ):
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not installed — BrowserScraper unavailable")
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.wait_for_js = wait_for_js
        self.remove_overlays = remove_overlays

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
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
        except Exception as exc:
            logger.warning(f"Failed to remove overlays: {exc}")

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
    ) -> Union[str, Tuple[str, List[Dict[str, Union[str, int]]]]]:
        if not self._context:
            raise RuntimeError("BrowserScraper context is not initialized")

        page = self._context.new_page()
        try:
            page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
            if self.wait_for_js:
                try:
                    page.wait_for_load_state("load", timeout=self.timeout_ms)
                    time.sleep(1)
                except Exception as exc:
                    logger.warning(f"Page load wait timeout for {url}: {exc}")

            if self.remove_overlays:
                self._remove_overlays(page)

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

    def __init__(
        self,
        css_selectors: Optional[List[str]] = None,
        use_visual_order: bool = False,
        wait_for_js: bool = True,
        remove_overlays: bool = True,
        browser_timeout: int = 30,
        exclude_selectors: Optional[List[str]] = None,
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
        self.chapters: List[Dict[str, str]] = []

    def scrape_chapters(self, urls: List[str]) -> List[Dict[str, str]]:
        return self._scrape_chapters_browser(urls)

    def scrape_index_page(self, index_url: str, max_pages: int = 50) -> List[str]:
        parsed_index = urlparse(index_url)
        base_url = f"{parsed_index.scheme}://{parsed_index.netloc}"
        host = parsed_index.netloc

        chapter_urls: List[str] = []
        seen_chapters: set[str] = set()
        seen_index_pages: set[str] = set()
        pages_to_visit = [index_url]

        with BrowserScraper(
            headless=True,
            timeout_ms=self.browser_timeout * 1000,
            wait_for_js=self.wait_for_js,
            remove_overlays=self.remove_overlays,
        ) as browser:
            page_count = 0
            while pages_to_visit and page_count < max_pages:
                current_page_url = pages_to_visit.pop(0)
                if current_page_url in seen_index_pages:
                    continue

                seen_index_pages.add(current_page_url)
                page_count += 1

                html = browser.scrape_page(current_page_url)
                soup = BeautifulSoup(html, "html.parser")

                page_chapters, next_page_links = self._extract_chapter_and_pagination_links(
                    soup,
                    current_page_url,
                    base_url,
                    host,
                    parsed_index.path,
                )

                for ch in page_chapters:
                    if ch not in seen_chapters:
                        seen_chapters.add(ch)
                        chapter_urls.append(ch)

                for next_link in next_page_links:
                    if next_link not in seen_index_pages and next_link not in pages_to_visit:
                        pages_to_visit.append(next_link)

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

            is_pagination = (
                any(k in link_text for k in ["next", "siguiente", "»", ">", "page"])
                or re.search(r"[?&](page|p)=\d+", href.lower())
                or re.search(r"/(page|p)/\d+", link_path)
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

    def _scrape_chapters_browser(self, urls: List[str]) -> List[Dict[str, str]]:
        with BrowserScraper(
            headless=True,
            timeout_ms=self.browser_timeout * 1000,
            wait_for_js=self.wait_for_js,
            remove_overlays=self.remove_overlays,
        ) as browser:
            for url in urls:
                try:
                    self.chapters.append(self._scrape_single_browser(url, browser))
                except Exception as exc:
                    logger.error(f"Error scraping {url}: {exc}")
        return self.chapters

    def _scrape_single_browser(self, url: str, browser: BrowserScraper) -> Dict[str, str]:
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