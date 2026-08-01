# ebook_app/phases/phase8_output.py
"""Phase 8 — Output.

Assembles the final EPUB3 audiobook from:
  - cleaned chapter XHTML
  - chapter audio WAV files
  - timing metadata (SMIL)
  - cover image (if present)
  - ToC metadata

Also copies the finished audio files to the output directory.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from ebook_app.phases.phase_base import PhaseBase, PhaseResult

logger = logging.getLogger(__name__)


class Phase8Output(PhaseBase):
    """Phase 8: assemble EPUB and copy final audio output."""

    def run(self, chapter_id: str = "", **kwargs) -> PhaseResult:
        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        chapters: List[Dict] = kwargs.get("chapters", [])
        output_dir: Any = kwargs.get("output_dir", "output")
        work_dir: Any = kwargs.get("work_dir")
        book_title: str = kwargs.get("book_title", "Untitled Book")
        book_author: str = kwargs.get("book_author", "Unknown Author")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        self._emit_progress(10)

        epub_path: Optional[str] = None
        audio_files: List[str] = []

        # Collect audio files from work_dir/audio/
        if work_dir:
            audio_src = Path(work_dir) / "audio"
            if audio_src.exists():
                audio_dest = output_dir / "audio"
                audio_dest.mkdir(parents=True, exist_ok=True)
                for wav in sorted(audio_src.rglob("*.wav")):
                    dest = audio_dest / wav.name
                    try:
                        shutil.copy2(wav, dest)
                        audio_files.append(str(dest))
                    except Exception as exc:
                        logger.warning("[Phase8] Could not copy %s: %s", wav, exc)

        self._emit_progress(40)

        if self.is_cancelled():
            return PhaseResult.cancelled_result()

        # Build EPUB
        try:
            from ebook_app.epub.packaging import EPUBBuilder

            builder = EPUBBuilder(
                title=book_title,
                author=book_author,
                output_dir=str(output_dir),
                work_dir=str(work_dir) if work_dir else str(output_dir),
            )
            epub_path = builder.build(chapters=chapters)
        except Exception as exc:
            logger.error("[Phase8] EPUB build failed: %s", exc, exc_info=True)
            # EPUB failure is non-fatal; audio output is still useful.
            epub_path = None

        self._emit_progress(100)

        lines = [f"Output directory: {output_dir}"]
        if epub_path:
            lines.append(f"EPUB:  {epub_path}")
        lines.append(f"Audio files exported: {len(audio_files)}")

        return PhaseResult(
            success=True,
            output_text="\n".join(lines),
            data={
                "epub_path": epub_path or "",
                "audio_files": audio_files,
                "output_dir": str(output_dir),
            },
        )
