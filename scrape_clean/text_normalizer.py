# ebook_app/text/parse/text_normalizer.py
"""Text normalization utilities for post-scrape/pre-translation cleanup."""
from __future__ import annotations
import re
import unicodedata


class TextNormalizer:
    """Normalize and clean text before processing."""

    @staticmethod
    def normalize_unicode(text: str) -> str:
        """Apply NFC Unicode normalization."""
        return unicodedata.normalize("NFC", text)

    @staticmethod
    def fix_punctuation(text: str) -> str:
        """Replace curly quotes, em-dashes, and other typographic characters."""
        replacements = {
            "‘": "'", "’": "'",   # curly single quotes
            "“": '"', "”": '"',   # curly double quotes
            "—": "—",                   # em-dash (keep)
            "–": "–",                   # en-dash (keep)
            "…": "...",                 # ellipsis
            " ": " ",                   # non-breaking space
        }
        for src, dst in replacements.items():
            text = text.replace(src, dst)
        return text

    @staticmethod
    def strip_html_entities(text: str) -> str:
        """Decode common HTML entities remaining after parsing."""
        import html
        return html.unescape(text)

    @staticmethod
    def collapse_blank_lines(text: str, max_blank: int = 2) -> str:
        """Reduce consecutive blank lines to at most *max_blank* lines."""
        pattern = r"\n{%d,}" % (max_blank + 1)
        replacement = "\n" * max_blank
        return re.sub(pattern, replacement, text)

    @classmethod
    def normalize(cls, text: str) -> str:
        """Apply all normalization steps in order."""
        text = cls.strip_html_entities(text)
        text = cls.normalize_unicode(text)
        text = cls.fix_punctuation(text)
        text = cls.collapse_blank_lines(text)
        return text.strip()
