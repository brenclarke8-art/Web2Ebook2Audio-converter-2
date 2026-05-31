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
        from urllib.parse import urljoin
        return urljoin(base, link)

    # Required by pipeline controller:
    def scrape_index_page(self, url: str, max_pages: int = 50):
        raise NotImplementedError

    def scrape_chapters(self, urls: List[str]):
        raise NotImplementedError
