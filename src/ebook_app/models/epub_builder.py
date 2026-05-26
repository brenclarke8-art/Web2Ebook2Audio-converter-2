from __future__ import annotations
from pathlib import Path
import zipfile
import uuid
from typing import List, Dict

from ebook_app.models.media_overlay import MediaOverlayBuilder, TextSegment


class EPUBBuilder:
    """
    Builds EPUB3 files with optional Media Overlays (audio/text sync).
    """

    def __init__(self, title: str, author: str, output_dir: str):
        self.title = title
        self.author = author
        self.output_dir = Path(output_dir)
        self.book_id = str(uuid.uuid4())

        self.chapters: List[Dict] = []
        self.audio_files: Dict[str, str] = {}
        self.smil_files: Dict[str, str] = {}

    def add_chapter(self, filename: str, xhtml: str):
        self.chapters.append({
            "filename": filename,
            "xhtml": xhtml
        })

    def add_audio(self, chapter_filename: str, audio_path: str, segments: List[TextSegment]):
        """
        Adds audio + generates SMIL overlay.
        """
        audio_name = Path(audio_path).name
        self.audio_files[chapter_filename] = audio_name

        smil_name = chapter_filename.replace(".xhtml", "_overlay.smil")
        smil_xml = MediaOverlayBuilder.build_smil(
            chapter_filename=chapter_filename,
            audio_filename=audio_name,
            segments=segments
        )

        self.smil_files[chapter_filename] = (smil_name, smil_xml)

    def build(self) -> Path:
        """
        Creates the EPUB file.
        """
        out_path = self.output_dir / f"{self.title}.epub"

        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            # Required mimetype file (must be uncompressed)
            z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

            # META-INF/container.xml
            z.writestr("META-INF/container.xml", self._container_xml())

            # OEBPS content
            for chapter in self.chapters:
                z.writestr(f"OEBPS/{chapter['filename']}", chapter["xhtml"])

            for chapter_filename, audio_name in self.audio_files.items():
                audio_path = self.output_dir / audio_name
                z.write(audio_path, f"OEBPS/{audio_name}")

            for chapter_filename, (smil_name, smil_xml) in self.smil_files.items():
                z.writestr(f"OEBPS/{smil_name}", smil_xml)

            # content.opf
            z.writestr("OEBPS/content.opf", self._content_opf())

        return out_path

    # ---------------------------------------------------------
    # XML Builders
    # ---------------------------------------------------------

    def _container_xml(self) -> str:
        return f"""<?xml version="1.0"?>
<container version="1.0"
    xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf"
              media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

    def _content_opf(self) -> str:
        manifest_items = []
        spine_items = []

        for chapter in self.chapters:
            fn = chapter["filename"]
            manifest_items.append(
                f'<item id="{fn}" href="{fn}" media-type="application/xhtml+xml"/>'
            )
            spine_items.append(
                f'<itemref idref="{fn}" media-overlay="{fn}_overlay"/>'
                if fn in self.smil_files
                else f'<itemref idref="{fn}"/>'
            )

        for chapter_filename, audio_name in self.audio_files.items():
            manifest_items.append(
                f'<item id="{audio_name}" href="{audio_name}" media-type="audio/mpeg"/>'
            )

        for chapter_filename, (smil_name, _) in self.smil_files.items():
            manifest_items.append(
                f'<item id="{smil_name}" href="{smil_name}" media-type="application/smil+xml"/>'
            )

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<package version="3.0"
         xmlns="http://www.idpf.org/2007/opf"
         unique-identifier="bookid">

  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{self.title}</dc:title>
    <dc:creator>{self.author}</dc:creator>
    <dc:identifier id="bookid">{self.book_id}</dc:identifier>
  </metadata>

  <manifest>
    {''.join(manifest_items)}
  </manifest>

  <spine>
    {''.join(spine_items)}
  </spine>

</package>
"""
