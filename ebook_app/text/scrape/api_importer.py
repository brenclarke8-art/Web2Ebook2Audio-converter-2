# ebook_app/text/scrape/api_importer.py
"""API importer — fetches chapter content from a REST/JSON API."""
from __future__ import annotations
from typing import Any, Callable, List, Optional
import requests


class ApiImporter:
    """Fetch chapters from a REST API that returns JSON."""

    def __init__(
        self,
        base_url: str,
        chapter_endpoint: str = "/chapters",
        headers: Optional[dict] = None,
        timeout: int = 30,
        transform: Optional[Callable[[Any], dict]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.chapter_endpoint = chapter_endpoint
        self.headers = headers or {}
        self.timeout = timeout
        self.transform = transform

    def extract_chapters(self) -> List[dict]:
        url = f"{self.base_url}{self.chapter_endpoint}"
        response = requests.get(url, headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        if self.transform:
            return [self.transform(item) for item in data]
        return data
