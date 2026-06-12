# ebook_app/epub/opf_builder.py
"""OPF (Open Packaging Format) builder for EPUB3."""
from __future__ import annotations
import html
from datetime import datetime, timezone
from typing import Dict, List
import xml.etree.ElementTree as ET


def build_opf(
    *,
    title: str,
    author: str,
    book_uuid: str,
    chapters: List[Dict],
    has_smil: bool = False,
    modified: str | None = None,
) -> str:
    """Build the content.opf Package Document as an XML string."""
    if modified is None:
        modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    ns = {
        "": "http://www.idpf.org/2007/opf",
        "dc": "http://purl.org/dc/elements/1.1/",
        "dcterms": "http://purl.org/dc/terms/",
    }
    ET.register_namespace("", ns[""])
    ET.register_namespace("dc", ns["dc"])
    ET.register_namespace("dcterms", ns["dcterms"])

    pkg = ET.Element("package", {
        "xmlns": ns[""],
        "version": "3.0",
        "unique-identifier": "bookid",
    })

    # <metadata>
    meta = ET.SubElement(pkg, "metadata", {
        "xmlns:dc": ns["dc"],
        "xmlns:dcterms": ns["dcterms"],
    })
    id_el = ET.SubElement(meta, "{%s}identifier" % ns["dc"], {"id": "bookid"})
    id_el.text = f"urn:uuid:{book_uuid}"
    title_el = ET.SubElement(meta, "{%s}title" % ns["dc"])
    title_el.text = title
    author_el = ET.SubElement(meta, "{%s}creator" % ns["dc"])
    author_el.text = author
    lang_el = ET.SubElement(meta, "{%s}language" % ns["dc"])
    lang_el.text = "en"
    ET.SubElement(meta, "meta", {"property": "dcterms:modified"}).text = modified

    # <manifest>
    manifest = ET.SubElement(pkg, "manifest")
    ET.SubElement(manifest, "item", {
        "id": "nav",
        "href": "nav.xhtml",
        "media-type": "application/xhtml+xml",
        "properties": "nav",
    })
    ET.SubElement(manifest, "item", {
        "id": "css",
        "href": "css/stylesheet.css",
        "media-type": "text/css",
    })
    for ch in chapters:
        fname = ch["filename"]
        item_id = fname.replace(".", "_")
        attrs = {
            "id": item_id,
            "href": f"text/{fname}",
            "media-type": "application/xhtml+xml",
        }
        if has_smil and ch.get("smil_filename"):
            attrs["media-overlay"] = ch["smil_filename"].replace(".", "_")
        ET.SubElement(manifest, "item", attrs)
        if ch.get("audio_filename"):
            audio_fname = ch["audio_filename"]
            # Determine media-type from file extension
            if audio_fname.lower().endswith(".wav"):
                audio_media_type = "audio/wav"
            elif audio_fname.lower().endswith(".ogg"):
                audio_media_type = "audio/ogg"
            else:
                audio_media_type = "audio/mpeg"
            ET.SubElement(manifest, "item", {
                "id": audio_fname.replace(".", "_"),
                "href": f"audio/{audio_fname}",
                "media-type": audio_media_type,
            })
        if has_smil and ch.get("smil_filename"):
            ET.SubElement(manifest, "item", {
                "id": ch["smil_filename"].replace(".", "_"),
                "href": f"smil/{ch['smil_filename']}",
                "media-type": "application/smil+xml",
            })

    # <spine>
    spine = ET.SubElement(pkg, "spine")
    for ch in chapters:
        ET.SubElement(spine, "itemref", {"idref": ch["filename"].replace(".", "_")})

    xml_str = ET.tostring(pkg, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str
