"""
Phase 02 — Text Normalization Processor

Copilot Instructions:
- Follow Phase 00 and Phase 01 processor.py EXACTLY.
- Rewrite normalization logic using legacy code ONLY as reference:
    legacy/ebook_app/clean/*
    legacy/ebook_app/parse/*
    legacy/ebook_app/text/*
- Do NOT import legacy code.
- Do NOT perform filesystem writes.
- Do NOT perform logging.
- Do NOT perform network calls.
- All logic must be PURE and DETERMINISTIC.
"""

import html
import re
import time
import sys
from html.parser import HTMLParser

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from .input_schema import Phase02Input
from .output_schema import Phase02Output


REMOVABLE_TEXT = {
    "sponsored content",
    "next chapter",
    "previous chapter",
    "table of contents",
    "chapter navigation",
}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "div", "br", "li", "tr", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"p", "div", "li", "tr", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n")

    def handle_data(self, data):
        if data:
            self._parts.append(data)

    def get_text(self):
        return "".join(self._parts)


def _strip_html(raw: str) -> str:
    """Strip HTML markup and keep readable text blocks while removing obvious boilerplate."""
    if raw is None:
        return ""

    text = str(raw)
    text = re.sub(r"(?is)<(script|style)\b.*?>.*?</\1>", " ", text)
    text = re.sub(r"(?is)<!--.*?-->", " ", text)

    parser = _HTMLTextExtractor()
    parser.feed(text)
    parser.close()
    text = parser.get_text()

    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\r\n?", "\n", text)

    for marker in sorted(REMOVABLE_TEXT, key=len, reverse=True):
        text = re.sub(rf"(?is)\b{re.escape(marker)}\b", " ", text)

    return text.strip()


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace while preserving paragraph breaks."""
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[\t\f\v]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ ]{2,}", " ", text)

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    normalized = "\n\n".join(paragraphs)
    return normalized.strip()


def _compute_stats(text: str) -> dict:
    """Compute deterministic chapter statistics."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    words = re.findall(r"\b\w+\b", text)
    return {
        "length": len(text),
        "word_count": len(words),
        "paragraph_count": len(paragraphs),
        "sentence_count": len(re.split(r"(?<=[.!?])\s+", text.strip())) if text.strip() else 0,
    }


def process(input_data: Phase02Input) -> Phase02Output:
    start = time.time()

    normalized = {}
    stats = {}

    for chapter in input_data.chapter_index:
        cid = chapter.get("chapter_id")
        if not cid:
            continue

        raw = input_data.raw_payloads.get(cid, "")
        cleaned = _strip_html(raw)
        cleaned = _normalize_whitespace(cleaned)

        normalized[cid] = cleaned
        stats[cid] = _compute_stats(cleaned)

    output = Phase02Output(
        normalized_chapters=normalized,
        chapter_stats=stats,
        meta={
            "phase": "02_cleaning",
            "version": "1.0.0",
            "timestamp": time.time(),
        },
        input_summary={
            "chapter_count": len(input_data.chapter_index),
            "payload_count": len(input_data.raw_payloads),
        },
        output_summary={
            "normalized_count": len(normalized),
        },
        errors=[],
        warnings=[],
        timings={"total_ms": (time.time() - start) * 1000},
    )

    return output
