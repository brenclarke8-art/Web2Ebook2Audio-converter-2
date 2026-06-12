# ebook_app/text/scrape/epub_importer.py
"""EPUB file importer — extracts chapters from .epub files."""
from __future__ import annotations
from pathlib import Path
from typing import List


class EpubImporter:
    """Import and extract chapter text from EPUB files."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def extract_chapters(self) -> List[dict]:
        """
        Returns a list of chapter dicts with keys: title, content.
        Requires ``ebooklib`` to be installed.
        """
        try:
            import ebooklib
            from ebooklib import epub
            from bs4 import BeautifulSoup
        except ImportError as exc:
            raise ImportError("ebooklib and beautifulsoup4 are required for EPUB import") from exc

        book = epub.read_epub(str(self.path))
        chapters = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_content(), "html.parser")
            text = soup.get_text(separator="\n")
            title = soup.find(["h1", "h2", "h3"])
            chapters.append({
                "title": title.get_text(strip=True) if title else item.get_name(),
                "content": text.strip(),
            })
        return chapters
