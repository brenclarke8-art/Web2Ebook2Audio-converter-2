# ebook_app/epub/smil_builder.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List
import xml.etree.ElementTree as ET


@dataclass
class TextSegment:
    paragraph_id: str
    clip_begin: float
    clip_end: float


class MediaOverlayBuilder:
    """
    Builds EPUB3 Media Overlay (SMIL) files from:
    - paragraph IDs
    - audio timestamps
    """

    @staticmethod
    def build_smil(chapter_filename: str, audio_filename: str, segments: List[TextSegment]) -> str:
        """
        Returns SMIL XML as a string.
        """

        ns = {
            "smil": "http://www.w3.org/2001/SMIL20/",
            "epub": "http://www.idpf.org/2007/ops"
        }

        ET.register_namespace("", ns["smil"])
        ET.register_namespace("epub", ns["epub"])

        # Root <smil>
        smil = ET.Element("smil", {
            "xmlns": ns["smil"],
            "xmlns:epub": ns["epub"],
            "version": "3.0"
        })

        # <head> block (recommended for EPUB3)
        head = ET.SubElement(smil, "head")
        ET.SubElement(head, "meta", {
            "name": "dc:format",
            "content": "application/smil+xml"
        })

        # <body>
        body = ET.SubElement(smil, "body")

        # Main sequence
        seq = ET.SubElement(body, "seq", {
            "id": "seq1",
            "epub:textref": chapter_filename,
            "epub:type": "bodymatter"
        })

        # Build <par> entries
        for seg in segments:
            par = ET.SubElement(seq, "par")

            ET.SubElement(par, "text", {
                "src": f"{chapter_filename}#{seg.paragraph_id}"
            })

            ET.SubElement(par, "audio", {
                "src": audio_filename,
                "clipBegin": MediaOverlayBuilder._fmt(seg.clip_begin),
                "clipEnd": MediaOverlayBuilder._fmt(seg.clip_end)
            })

        # Pretty-print XML
        xml_string = ET.tostring(smil, encoding="unicode")

        # Add XML declaration manually
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_string

    @staticmethod
    def _fmt(seconds: float) -> str:
        """
        Format seconds as HH:MM:SS.mmm
        """
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h:02}:{m:02}:{s:06.3f}"
