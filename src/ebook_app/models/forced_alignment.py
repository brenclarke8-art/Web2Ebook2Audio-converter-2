# src/ebook_app/models/forced_alignment.py
"""Placeholder forced-alignment module for generating word/paragraph timestamps."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AlignmentEntry:
    """Timing entry for a single text span.

    :param paragraph_id: ID matching the XHTML ``id`` attribute.
    :param start_s:      Start time in seconds.
    :param end_s:        End time in seconds.
    :param text:         The aligned text (for debugging).
    """

    paragraph_id: str
    start_s: float
    end_s: float
    text: str = ""


class ForcedAlignment:
    """Generates :class:`AlignmentEntry` objects from an audio file and transcript.

    TODO: integrate a real forced-alignment library (e.g. WhisperX, CTC-segmentation).

    Usage::

        aligner = ForcedAlignment()
        entries = aligner.align(wav_path="chapter01.wav", segments=segments)
    """

    def align(
        self,
        wav_path: str,
        segments: list,  # list[Segment] — avoiding circular import
        chapter_id: str = "ch",
    ) -> list[AlignmentEntry]:
        """Align *segments* to the audio at *wav_path*.

        :param wav_path:   Path to the WAV file produced by TTS.
        :param segments:   Ordered list of :class:`~ebook_app.models.dialogue_parser.Segment`.
        :param chapter_id: Short prefix for paragraph IDs.
        :returns:          One :class:`AlignmentEntry` per segment, with placeholder timings.

        TODO: call a real aligner and populate start_s / end_s from the result.
        """
        entries: list[AlignmentEntry] = []
        # Placeholder: distribute segments evenly across a 60-second window.
        step = 60.0 / max(len(segments), 1)
        for i, seg in enumerate(segments):
            entries.append(
                AlignmentEntry(
                    paragraph_id=seg.paragraph_id or f"{chapter_id}_p{i}",
                    start_s=round(i * step, 3),
                    end_s=round((i + 1) * step, 3),
                    text=seg.text[:80],
                )
            )
        return entries
