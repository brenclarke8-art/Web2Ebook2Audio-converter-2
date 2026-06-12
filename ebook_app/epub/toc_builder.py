# ebook_app/epub/toc_builder.py
"""Legacy NCX TOC builder (EPUB2 compatibility)."""
from __future__ import annotations
import html
from typing import Dict, List
import xml.etree.ElementTree as ET


def build_ncx(
    *,
    title: str,
    author: str,
    book_uuid: str,
    chapters: List[Dict],
) -> str:
    """Build the toc.ncx Navigation Control document as an XML string."""
    ET.register_namespace("", "http://www.daisy.org/z3986/2005/ncx/")

    ncx = ET.Element("ncx", {
        "xmlns": "http://www.daisy.org/z3986/2005/ncx/",
        "version": "2005-1",
    })

    head = ET.SubElement(ncx, "head")
    ET.SubElement(head, "meta", {"name": "dtb:uid",   "content": f"urn:uuid:{book_uuid}"})
    ET.SubElement(head, "meta", {"name": "dtb:depth", "content": "1"})
    ET.SubElement(head, "meta", {"name": "dtb:totalPageCount", "content": "0"})
    ET.SubElement(head, "meta", {"name": "dtb:maxPageNumber",  "content": "0"})

    doc_title = ET.SubElement(ncx, "docTitle")
    ET.SubElement(doc_title, "text").text = title

    nav_map = ET.SubElement(ncx, "navMap")
    for i, ch in enumerate(chapters, start=1):
        nav_point = ET.SubElement(nav_map, "navPoint", {
            "id": f"navPoint-{i}",
            "playOrder": str(i),
        })
        nav_label = ET.SubElement(nav_point, "navLabel")
        ET.SubElement(nav_label, "text").text = ch["title"]
        ET.SubElement(nav_point, "content", {"src": f"text/{ch['filename']}"})

    xml_str = ET.tostring(ncx, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
