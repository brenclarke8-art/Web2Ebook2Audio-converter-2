"""Scraping and text-cleaning pipeline module."""

from .api_importer import ApiImporter
from .base_scraper import BaseScraper
from .browser_scraper import WebScraper, BrowserSessionManager
from .chapter_detection import ChapterInfo, ChapterIterator
from .epub_importer import EpubImporter
from .file_importer import FileImporter
from .html_cleaner import TextCleaner, extract_main_content_by_structure
from .ocr_importer import OcrImporter
from .parser import Chapter
from .pdf_importer import PdfImporter
from .text_normalizer import TextNormalizer
from .web_scraper import HttpWebScraper

__all__ = [
    "ApiImporter",
    "BaseScraper",
    "BrowserSessionManager",
    "Chapter",
    "ChapterInfo",
    "ChapterIterator",
    "EpubImporter",
    "FileImporter",
    "HttpWebScraper",
    "OcrImporter",
    "PdfImporter",
    "TextCleaner",
    "TextNormalizer",
    "WebScraper",
    "extract_main_content_by_structure",
]
