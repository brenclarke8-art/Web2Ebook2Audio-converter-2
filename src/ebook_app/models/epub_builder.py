from __future__ import annotations
from pathlib import Path
import zipfile
import uuid
from typing import List, Dict, Optional
from datetime import datetime

from ebook_app.models.media_overlay import MediaOverlayBuilder, TextSegment


class EPUBBuilder:
    """
    Builds EPUB3 files with optional Media Overlays (audio/text sync).
    """

    def __init__(
        self,
        title: str,
        author: str,
        output_dir: str,
        language: str = "en",
        publisher: str = "",
        cover_path: Optional[str] = None,
        work_dir: Optional[str] = None,
    ):
        self.title = title
        self.author = author
        self.output_dir = Path(output_dir)
        self.book_id = str(uuid.uuid4())
        self.language = language
        self.publisher = publisher
        self.cover_path = Path(cover_path) if cover_path else None

        # Work directory used by the pipeline (for audio, etc.)
        # If not provided, default to output_dir / "pipeline_work"
        self.work_dir = Path(work_dir) if work_dir else (self.output_dir / "pipeline_work")

        self.chapters: List[Dict] = []
        # chapter_filename -> audio file name (e.g. "ch001.wav")
        self.audio_files: Dict[str, str] = {}
        # chapter_filename -> (smil_name, smil_xml)
        self.smil_files: Dict[str, tuple[str, str]] = {}

    def add_chapter(self, filename: str, xhtml: str, title: str = ""):
        """Add a chapter to the EPUB."""
        self.chapters.append({
            "filename": filename,
            "xhtml": xhtml,
            "title": title or filename.replace(".xhtml", "").replace("_", " ").title(),
        })

    def add_audio(self, chapter_filename: str, audio_path: str, segments: List[TextSegment]):
        """
        Adds audio + generates SMIL overlay.

        chapter_filename: the XHTML filename (e.g. "ch001.xhtml")
        audio_path: path to the chapter audio file on disk (ignored for path resolution,
                    but kept for future compatibility if needed)
        segments: list of TextSegment for SMIL overlay
        """
        audio_name = Path(audio_path).name
        self.audio_files[chapter_filename] = audio_name

        smil_name = chapter_filename.replace(".xhtml", "_overlay.smil")

        # Audio inside the EPUB will live under OEBPS/audio/
        # SMIL must reference it with a relative path.
        smil_xml = MediaOverlayBuilder.build_smil(
            chapter_filename=chapter_filename,
            audio_filename=f"audio/{audio_name}",
            segments=segments,
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

            # CSS stylesheet
            z.writestr("OEBPS/stylesheet.css", self._stylesheet_css())

            # Cover image if provided
            if self.cover_path and self.cover_path.exists():
                cover_ext = self.cover_path.suffix.lower()
                cover_name = f"cover{cover_ext}"
                z.write(self.cover_path, f"OEBPS/{cover_name}")

            # Navigation document (EPUB3 nav.xhtml)
            z.writestr("OEBPS/nav.xhtml", self._nav_xhtml())

            # TOC (toc.xhtml for compatibility)
            z.writestr("OEBPS/toc.xhtml", self._toc_xhtml())

            # OEBPS content chapters
            for chapter in self.chapters:
                z.writestr(f"OEBPS/{chapter['filename']}", chapter["xhtml"])

            # Audio files (stored under OEBPS/audio/)
            for chapter_filename, audio_name in self.audio_files.items():
                chapter_id = Path(chapter_filename).stem  # e.g. "ch001"
                audio_path = self.work_dir / "audio" / chapter_id / audio_name
                if audio_path.exists():
                    z.write(audio_path, f"OEBPS/audio/{audio_name}")

            # SMIL files
            for _, (smil_name, smil_xml) in self.smil_files.items():
                z.writestr(f"OEBPS/{smil_name}", smil_xml)

            # content.opf
            z.writestr("OEBPS/content.opf", self._content_opf())

        return out_path

    # ---------------------------------------------------------
    # XML Builders
    # ---------------------------------------------------------

    def _container_xml(self) -> str:
        return """<?xml version="1.0"?>
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

        # Add navigation documents
        manifest_items.append(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        )
        manifest_items.append(
            '<item id="toc" href="toc.xhtml" media-type="application/xhtml+xml"/>'
        )

        # Add stylesheet
        manifest_items.append(
            '<item id="stylesheet" href="stylesheet.css" media-type="text/css"/>'
        )

        # Add cover image if provided
        has_cover = False
        if self.cover_path and self.cover_path.exists():
            has_cover = True
            cover_ext = self.cover_path.suffix.lower()
            cover_name = f"cover{cover_ext}"
            media_type = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
            }.get(cover_ext, "image/jpeg")
            manifest_items.append(
                f'<item id="cover-image" href="{cover_name}" media-type="{media_type}" properties="cover-image"/>'
            )

        # Add chapters
        for chapter in self.chapters:
            fn = chapter["filename"]
            manifest_items.append(
                f'<item id="{fn}" href="{fn}" media-type="application/xhtml+xml"/>'
            )
            if fn in self.smil_files:
                smil_name, _ = self.smil_files[fn]
                spine_items.append(
                    f'<itemref idref="{fn}" media-overlay="{smil_name}"/>'
                )
            else:
                spine_items.append(f'<itemref idref="{fn}"/>')

        # Add audio files (under audio/)
        for _, audio_name in self.audio_files.items():
            manifest_items.append(
                f'<item id="{audio_name}" href="audio/{audio_name}" media-type="audio/wave"/>'
            )

        # Add SMIL files
        for _, (smil_name, _) in self.smil_files.items():
            manifest_items.append(
                f'<item id="{smil_name}" href="{smil_name}" media-type="application/smil+xml"/>'
            )

        # Build metadata
        date_now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        metadata = f"""  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{self._escape_xml(self.title)}</dc:title>
    <dc:creator>{self._escape_xml(self.author)}</dc:creator>
    <dc:identifier id="bookid">{self.book_id}</dc:identifier>
    <dc:language>{self.language}</dc:language>
    <dc:date>{date_now}</dc:date>"""

        if self.publisher:
            metadata += f"\n    <dc:publisher>{self._escape_xml(self.publisher)}</dc:publisher>"

        # Kindle-compatible cover metadata
        if has_cover:
            metadata += '\n    <meta name="cover" content="cover-image"/>'

        metadata += '\n    <meta property="dcterms:modified">{}</meta>'.format(date_now)
        metadata += "\n  </metadata>"

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<package version="3.0"
         xmlns="http://www.idpf.org/2007/opf"
         unique-identifier="bookid">

{metadata}

  <manifest>
    {'\n    '.join(manifest_items)}
  </manifest>

  <spine>
    {'\n    '.join(spine_items)}
  </spine>

</package>
"""

    def _nav_xhtml(self) -> str:
        """Generate EPUB3 navigation document."""
        nav_items = []
        for i, chapter in enumerate(self.chapters, 1):
            title = self._escape_xml(chapter.get("title", f"Chapter {i}"))
            filename = chapter["filename"]
            nav_items.append(f'      <li><a href="{filename}">{title}</a></li>')

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>Navigation</title>
    <link rel="stylesheet" type="text/css" href="stylesheet.css"/>
</head>
<body>
    <nav epub:type="toc" id="toc">
        <h1>Table of Contents</h1>
        <ol>
{chr(10).join(nav_items)}
        </ol>
    </nav>
</body>
</html>"""

    def _toc_xhtml(self) -> str:
        """Generate legacy TOC for EPUB2 compatibility."""
        toc_items = []
        for i, chapter in enumerate(self.chapters, 1):
            title = self._escape_xml(chapter.get("title", f"Chapter {i}"))
            filename = chapter["filename"]
            toc_items.append(f'      <li><a href="{filename}">{title}</a></li>')

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>Table of Contents</title>
    <link rel="stylesheet" type="text/css" href="stylesheet.css"/>
</head>
<body>
    <h1>Table of Contents</h1>
    <ol>
{chr(10).join(toc_items)}
    </ol>
</body>
</html>"""

    def _stylesheet_css(self) -> str:
        """Generate basic CSS stylesheet for EPUB."""
        return """/* EPUB Stylesheet */

body {
    font-family: Georgia, serif;
    font-size: 1.1em;
    line-height: 1.6;
    margin: 1em;
    text-align: justify;
}

h1 {
    font-size: 1.8em;
    font-weight: bold;
    margin-top: 1em;
    margin-bottom: 0.5em;
    text-align: center;
}

h2 {
    font-size: 1.4em;
    font-weight: bold;
    margin-top: 1em;
    margin-bottom: 0.5em;
}

p {
    margin-top: 0;
    margin-bottom: 1em;
    text-indent: 1.5em;
}

p:first-of-type {
    text-indent: 0;
}

a {
    color: #0066cc;
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

nav ol {
    list-style-type: none;
    padding-left: 0;
}

nav li {
    margin-bottom: 0.5em;
}
"""

    @staticmethod
    def _escape_xml(text: str) -> str:
        """Escape XML special characters."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )
