# src/ebook_app/models/media_overlay.py
"""EPUB3 Media Overlay helpers — XHTML generator and SMIL builder."""

from __future__ import annotations

from dataclasses import dataclass

from ebook_app.models.forced_alignment import AlignmentEntry


@dataclass
class SmilClip:
    """A single <par> clip inside a SMIL document.

    :param paragraph_id: Must match the ``id`` attribute in the XHTML file.
    :param audio_src:    Relative path to the audio file.
    :param clip_begin:   ``npt=`` start time string (e.g. ``"0.000s"``).
    :param clip_end:     ``npt=`` end time string.
    """

    paragraph_id: str
    audio_src: str
    clip_begin: str
    clip_end: str


def generate_xhtml(
    title: str,
    paragraphs: list[tuple[str, str]],
    language: str = "en",
) -> str:
    """Generate an EPUB3-compatible XHTML document.

    :param title:       Chapter title.
    :param paragraphs:  List of ``(paragraph_id, text)`` tuples.
    :param language:    BCP-47 language tag.
    :returns:           XHTML string.

    TODO: add media:overlay attribute to <body> once SMIL path is known.
    """
    para_lines = "\n".join(
        f'    <p id="{pid}">{_escape(text)}</p>'
        for pid, text in paragraphs
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{language}">
<head>
  <meta charset="utf-8"/>
  <title>{_escape(title)}</title>
</head>
<body>
  <h1>{_escape(title)}</h1>
{para_lines}
</body>
</html>"""


def build_smil(
    chapter_id: str,
    xhtml_src: str,
    audio_src: str,
    entries: list[AlignmentEntry],
) -> str:
    """Build a SMIL Media Overlay document from alignment entries.

    :param chapter_id: Used as the SMIL ``id``.
    :param xhtml_src:  Relative path to the XHTML chapter file.
    :param audio_src:  Relative path to the chapter audio file.
    :param entries:    :class:`AlignmentEntry` list from forced alignment.
    :returns:          SMIL XML string.

    TODO: validate against EPUB3 Media Overlays spec.
    """
    clips: list[SmilClip] = [
        SmilClip(
            paragraph_id=e.paragraph_id,
            audio_src=audio_src,
            clip_begin=f"npt={e.start_s:.3f}s",
            clip_end=f"npt={e.end_s:.3f}s",
        )
        for e in entries
    ]

    par_elements = "\n".join(
        f'    <par id="par_{c.paragraph_id}">\n'
        f'      <text src="{xhtml_src}#{c.paragraph_id}"/>\n'
        f'      <audio src="{c.audio_src}" clipBegin="{c.clip_begin}" clipEnd="{c.clip_end}"/>\n'
        f'    </par>'
        for c in clips
    )

    return f"""<?xml version="1.0" encoding="utf-8"?>
<smil xmlns="http://www.w3.org/ns/SMIL" version="3.0" id="{chapter_id}">
  <body>
    <seq id="seq_{chapter_id}">
{par_elements}
    </seq>
  </body>
</smil>"""


def _escape(text: str) -> str:
    """Minimal XML character escaping."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )
