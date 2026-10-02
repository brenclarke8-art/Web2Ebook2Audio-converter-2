# ebook_app/text/scrape/base_scraper.py
from __future__ import annotations
import logging
import time
from typing import List, Dict, Any
import requests
from bs4 import BeautifulSoup

from .errors import ScraperError

logger = logging.getLogger(__name__)

class BaseScraper:
    """
    Base class for HTTP scraping with retry logic and anti-detection headers.
    """

    # Rotate through realistic user-agent strings to reduce bot detection.
    _USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    ]
    _ua_index = 0

    @classmethod
    def _next_user_agent(cls) -> str:
        ua = cls._USER_AGENTS[cls._ua_index % len(cls._USER_AGENTS)]
        cls._ua_index += 1
        return ua

    @classmethod
    def _request_headers(cls) -> dict:
        return {
            "User-Agent": cls._next_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def fetch(self, url: str, *, timeout: int = 20) -> str:
        logger.debug(f"Fetching URL: {url}")
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.get(
                    url,
                    headers=self._request_headers(),
                    timeout=timeout,
                    allow_redirects=True,
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
        from urllib.parse import urljoin
        return urljoin(base, link)

    # Required by pipeline controller:
    def scrape_index_page(self, url: str, max_pages: int = 50):
        raise NotImplementedError

    def scrape_chapters(self, urls: List[str]):
        raise NotImplementedError
