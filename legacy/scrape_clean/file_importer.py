# ebook_app/text/scrape/file_importer.py
"""Plain-text file importer — reads .txt files as a single chapter."""
from __future__ import annotations
from pathlib import Path
from typing import List


class FileImporter:
    """Import plain-text files."""

    def __init__(self, path: str | Path, encoding: str = "utf-8"):
        self.path = Path(path)
        self.encoding = encoding

    def extract_chapters(self) -> List[dict]:
        text = self.path.read_text(encoding=self.encoding)
        return [{"title": self.path.stem, "content": text.strip()}]
