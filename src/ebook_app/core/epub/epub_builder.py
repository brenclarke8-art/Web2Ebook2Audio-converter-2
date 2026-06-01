from __future__ import annotations
import zipfile
from pathlib import Path
from typing import List, Dict
import xml.etree.ElementTree as ET

from ebook_app.pipeline_contracts import TextSegment


class EPUBBuilder:
    """
    Contract-compliant EPUB3 builder with Media Overlays (SMIL).
    """

    def __init__(
        self,
        *,
        title: str,
        author: str,
        output_dir: str,
        work_dir: str,
    ):
        self.title = title
        self.author = author
        self.output_dir = Path(output_dir)
        self.work_dir = Path(work_dir)

        self.oebps = self.work_dir / "OEBPS"
        self.text_dir = self.oebps / "text"
        self.audio_dir = self.oebps / "audio"
        self.smil_dir = self.oebps / "smil"
        self.meta_inf = self.work_dir / "META-INF"

        self.chapters: List[Dict] = []
        self.audio_map: Dict[str, Dict] = {}

        # Prepare directory structure
        self.text_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.smil_dir.mkdir(parents=True, exist_ok=True)
        self.meta_inf.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Contract: add_chapter
    # ------------------------------------------------------------------

    def add_chapter(self, *, filename: str, xhtml: str, title: str) -> None:
        out_path = self.text_dir / filename
        out_path.write_text(xhtml, encoding="utf-8")

        self.chapters.append({
            "filename": filename,
            "title": title,
        })

    # ------------------------------------------------------------------
    # Contract: add_audio
    # ------------------------------------------------------------------

    def add_audio(
        self,
        *,
        chapter_filename: str,
        audio_path: str,
        segments: List[TextSegment],
    ) -> None:
        # Copy audio file into OEBPS/audio/
        src = Path(audio_path)
        dest = self.audio_dir / src.name
        dest.write_bytes(src.read_bytes())

        # Store timing for SMIL generation
        self.audio_map[chapter_filename] = {
            "audio_file": dest.name,
            "segments": segments,
        }

    # ------------------------------------------------------------------
    # Contract: build
    # ------------------------------------------------------------------

    def build(self) -> Path:
        # Write SMIL files
        for chapter in self.chapters:
            self._write_smil_for_chapter(chapter["filename"])

        # Write nav.xhtml + content.opf + container.xml + mimetype
        self._write_nav()
        self._write_opf()
        self._write_container()
        self._write_mimetype()

        # Package EPUB
        out_path = self.output_dir / f"{self.title}.epub"
        self._zip_epub(out_path)

        return out_path

    # ------------------------------------------------------------------
    # SMIL generation
    # ------------------------------------------------------------------

    def _write_smil_for_chapter(self, chapter_filename: str) -> None:
        info = self.audio_map.get(chapter_filename)
        if not info:
            return

        audio_file = info["audio_file"]
        segments = info["segments"]

        chapter_id = Path(chapter_filename).stem
        smil_path = self.smil_dir / f"{chapter_id}.smil"

        root = ET.Element("smil", xmlns="http://www.w3.org/ns/SMIL")
        body = ET.SubElement(root, "body")
        seq = ET.SubElement(body, "seq")

        for seg in segments:
            par = ET.SubElement(seq, "par")

            ET.SubElement(
                par,
                "text",
                src=f"text/{chapter_filename}#{seg['paragraph_id']}",
            )

            ET.SubElement(
                par,
                "audio",
                src=f"audio/{audio_file}",
                clipBegin=str(seg["clip_begin"]),
                clipEnd=str(seg["clip_end"]),
            )

        tree = ET.ElementTree(root)
        tree.write(smil_path, encoding="utf-8", xml_declaration=True)

    # ------------------------------------------------------------------
    # nav.xhtml
    # ------------------------------------------------------------------

    def _write_nav(self) -> None:
        nav_path = self.oebps / "nav.xhtml"

        items = "\n".join(
            f'<li><a href="text/{c["filename"]}">{c["title"]}</a></li>'
            for c in self.chapters
        )

        nav_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Navigation</title></head>
  <body>
    <nav epub:type="toc" id="toc">
      <h1>Table of Contents</h1>
      <ol>
        {items}
      </ol>
    </nav>
  </body>
</html>
"""
        nav_path.write_text(nav_xhtml, encoding="utf-8")

    # ------------------------------------------------------------------
    # content.opf
    # ------------------------------------------------------------------

    def _write_opf(self) -> None:
        opf_path = self.oebps / "content.opf"

        manifest_items = []
        spine_items = []
        overlay_items = []

        for idx, c in enumerate(self.chapters):
            chapter_id = Path(c["filename"]).stem

            manifest_items.append(
                f'<item id="{chapter_id}" href="text/{c["filename"]}" media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'<itemref idref="{chapter_id}"/>')

            if c["filename"] in self.audio_map:
                manifest_items.append(
                    f'<item id="{chapter_id}_smil" href="smil/{chapter_id}.smil" '
                    f'media-type="application/smil+xml"/>'
                )
                overlay_items.append(
                    f'<itemref idref="{chapter_id}" properties="media-overlay"/>'
                )

        # Audio files
        for info in self.audio_map.values():
            manifest_items.append(
                f'<item id="{info["audio_file"]}" href="audio/{info["audio_file"]}" '
                f'media-type="audio/wav"/>'
            )

        manifest_xml = "\n".join(manifest_items)
        spine_xml = "\n".join(spine_items)

        opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0"
         unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{self.title}</dc:title>
    <dc:creator>{self.author}</dc:creator>
    <dc:identifier id="bookid">urn:uuid:12345</dc:identifier>
    <meta property="dcterms:modified">2025-01-01T00:00:00Z</meta>
  </metadata>

  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"
          properties="nav"/>
    {manifest_xml}
  </manifest>

  <spine>
    {spine_xml}
  </spine>
</package>
"""
        opf_path.write_text(opf, encoding="utf-8")

    # ------------------------------------------------------------------
    # container.xml
    # ------------------------------------------------------------------

    def _write_container(self) -> None:
        container_path = self.meta_inf / "container.xml"
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0"
           xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf"
              media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
        container_path.write_text(xml, encoding="utf-8")

    # ------------------------------------------------------------------
    # mimetype
    # ------------------------------------------------------------------

    def _write_mimetype(self) -> None:
        mimetype_path = self.work_dir / "mimetype"
        mimetype_path.write_text("application/epub+zip", encoding="utf-8")

    # ------------------------------------------------------------------
    # ZIP packaging
    # ------------------------------------------------------------------

    def _zip_epub(self, out_path: Path) -> None:
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            # mimetype must be first and uncompressed
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

            # Add META-INF
            for p in self.meta_inf.rglob("*"):
                z.write(p, p.relative_to(self.work_dir))

            # Add OEBPS
            for p in self.oebps.rglob("*"):
                z.write(p, p.relative_to(self.work_dir))
