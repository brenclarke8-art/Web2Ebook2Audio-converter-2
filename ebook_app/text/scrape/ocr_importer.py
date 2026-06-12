# ebook_app/text/scrape/ocr_importer.py
"""OCR importer — extracts text from image files using Tesseract OCR."""
from __future__ import annotations
from pathlib import Path
from typing import List


class OcrImporter:
    """Import text from images via OCR (requires pytesseract + Pillow)."""

    def __init__(self, path: str | Path, lang: str = "eng"):
        self.path = Path(path)
        self.lang = lang

    def extract_chapters(self) -> List[dict]:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise ImportError("pytesseract and Pillow are required for OCR import") from exc

        image = Image.open(str(self.path))
        text = pytesseract.image_to_string(image, lang=self.lang)
        return [{"title": self.path.stem, "content": text.strip()}]
