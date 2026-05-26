# src/ebook_app/models/epub_builder.py
"""EPUB3 builder — assembles chapters, audio, and SMIL into an .epub file."""

from __future__ import annotations

import uuid
from pathlib import Path


class EpubBuilder:
    """Packages XHTML chapters, WAV/MP3 audio, and SMIL overlays into an EPUB3 file.

    Usage::

        builder = EpubBuilder()
        epub_path = builder.build(
            chapter_dir="/project/chapters",
            audio_dir="/project/audio",
            output_path="/project/output/novel.epub",
            title="My Novel",
            author="Author Name",
        )

    TODO: use the ``ebooklib`` library (or direct ZIP construction) to produce
    a valid EPUB3 package with Media Overlays.
    """

    def build(
        self,
        chapter_dir: str,
        audio_dir: str,
        output_path: str,
        title: str = "Untitled",
        author: str = "Unknown",
        language: str = "en",
    ) -> str:
        """Build the EPUB3 file.

        :param chapter_dir:  Directory containing XHTML chapter files.
        :param audio_dir:    Directory containing synthesised WAV/MP3 files.
        :param output_path:  Destination .epub path.
        :param title:        Book title for OPF metadata.
        :param author:       Author name for OPF metadata.
        :param language:     BCP-47 language tag.
        :returns:            Absolute path to the generated .epub file.

        TODO: implement real EPUB packaging using ebooklib or zipfile.
        """
        # Placeholder: create an empty file so the service doesn't crash.
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            f"<!-- EPUB placeholder for '{title}' by {author} [id:{uuid.uuid4()}] -->",
            encoding="utf-8",
        )
        return str(out.resolve())

    # ------------------------------------------------------------------
    # Private helpers (stubs)
    # ------------------------------------------------------------------

    def _generate_opf(self, title: str, author: str, language: str, uid: str) -> str:
        """Generate the OPF package document XML.

        TODO: add manifest items for chapters, audio, SMIL, and NCX/nav.
        """
        return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{uid}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:language>{language}</dc:language>
  </metadata>
  <manifest/>
  <spine/>
</package>"""

    def _generate_container_xml(self) -> str:
        """Generate META-INF/container.xml pointing to content.opf."""
        return """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
