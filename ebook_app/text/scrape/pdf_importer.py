# ebook_app/text/scrape/pdf_importer.py
"""PDF file importer — extracts text from PDF files."""
from __future__ import annotations
from pathlib import Path
from typing import List


class PdfImporter:
    """Import and extract text from PDF files."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def extract_chapters(self) -> List[dict]:
        """
        Returns a list of page dicts with keys: title, content.
        Requires ``pdfminer.six`` or ``pypdf`` to be installed.
        """
        try:
            from pypdf import PdfReader
        except ImportError:
            try:
                from PyPDF2 import PdfReader  # type: ignore
            except ImportError as exc:
                raise ImportError("pypdf or PyPDF2 is required for PDF import") from exc

        reader = PdfReader(str(self.path))
        chapters = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            chapters.append({
                "title": f"Page {i + 1}",
                "content": text.strip(),
            })
        return chapters
