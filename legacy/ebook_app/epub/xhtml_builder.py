# ebook_app/epub/xhtml_builder.py
"""XHTML chapter builder for EPUB3."""
from __future__ import annotations
import html
from typing import Any, Dict, List


XHTML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
  <meta charset="UTF-8"/>
  <title>{title}</title>
  <link rel="stylesheet" type="text/css" href="../css/stylesheet.css"/>
</head>
<body epub:type="bodymatter">
{body}
</body>
</html>
"""


def build_chapter_xhtml(title: str, segments: List[Dict[str, Any]]) -> str:
    """
    Build an XHTML chapter from a list of text segments.

    Each segment dict should have at least: text, paragraph_id.
    Returns the complete XHTML string.
    """
    paragraphs = []
    for seg in segments:
        pid = seg.get("paragraph_id", "")
        text = html.escape(seg.get("text", ""))
        seg_type = seg.get("type", "narration")
        css_class = f"seg-{seg_type}" if seg_type != "narration" else "narration"
        if pid:
            paragraphs.append(f'  <p id="{pid}" class="{css_class}">{text}</p>')
        else:
            paragraphs.append(f'  <p class="{css_class}">{text}</p>')
    body = "\n".join(paragraphs)
    return XHTML_TEMPLATE.format(title=html.escape(title), body=body)


def build_nav_xhtml(title: str, chapters: List[Dict[str, str]]) -> str:
    """Build the EPUB3 nav.xhtml navigation document."""
    items = "\n".join(
        f'      <li><a href="text/{c["filename"]}">{html.escape(c["title"])}</a></li>'
        for c in chapters
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><meta charset="UTF-8"/><title>Table of Contents</title></head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>{html.escape(title)}</h1>
    <ol>
{items}
    </ol>
  </nav>
</body>
</html>
"""
