from __future__ import annotations
from typing import Dict

class Chapter:
    """Simple container for chapter data."""

    def __init__(self, url: str, title: str, content: str):
        self.url = url
        self.title = title
        self.content = content

    def to_dict(self) -> Dict[str, str]:
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content,
        }
