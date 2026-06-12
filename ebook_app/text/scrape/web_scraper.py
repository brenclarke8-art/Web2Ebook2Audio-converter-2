# ebook_app/text/scrape/web_scraper.py
from __future__ import annotations
import logging
import time
import re
from typing import List, Dict, Optional, Callable, Tuple
from urllib.parse import urlparse, urlunparse, urljoin

from bs4 import BeautifulSoup

from .base_scraper import BaseScraper
from .errors import ScraperError
from ebook_app.text.parse.html_cleaner import TextCleaner, extract_main_content_by_structure

logger = logging.getLogger(__name__)


class HttpWebScraper:
    """Lightweight scraper using requests + BeautifulSoup."""

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

                # Remove noise
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

                results.append({
                    "url": url,
                    "title": title,
                    "content": TextCleaner.clean_text(content),
                })

                logger.debug("HTTP chapter %d/%d OK: %s", idx, total, url)

            except Exception as exc:
                logger.error("HTTP chapter fetch failed %s: %s", url, exc)
                results.append({
                    "url": url,
                    "title": "Failed to scrape",
                    "content": "",
                    "error": str(exc),
                })

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

    def _extract_content(self, soup: BeautifulSoup) -> str:
        # 1. Honour explicit CSS selectors when provided
        if self.css_selectors:
            parts = []
            for sel in self.css_selectors:
                for el in soup.select(sel):
                    parts.append(el.get_text(separator="\n", strip=True))
            if parts:
                return "\n\n".join(parts)

        # 2. Structural / content-density heuristic (anti-scrape bypass)
        structural = extract_main_content_by_structure(soup)
        if structural:
            return structural

        # 3. Fallback: full body text
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
