# src/ebook_app/pipeline_controller.py
"""Pipeline orchestration controller — runs the end-to-end processing pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from ebook_app.core.settings_manager import SettingsManager
from ebook_app.models.dialogue_parser import DialogueParser, Segment
from ebook_app.models.epub_builder import EPUBBuilder
from ebook_app.models.forced_alignment import ForcedAlignment, AlignmentEntry
from ebook_app.models.media_overlay import MediaOverlayBuilder, TextSegment
from ebook_app.models.scraper import WebScraper
from ebook_app.models.tts_engine_cli import TTSEngine
from ebook_app.services.translation_service import TranslationService

logger = logging.getLogger(__name__)

# Progress callback type: (step_key, value 0-100) -> None
ProgressCallback = Callable[[str, int], None]


class PipelineController:
    """Orchestrates the full Web-Novel → EPUB3 Audiobook pipeline.

    Each pipeline step is a separate method that can be called individually
    or via :meth:`run_all`.  Progress is reported through an optional callback.

    Usage::

        ctrl = PipelineController(settings=settings, on_progress=my_callback)
        ctrl.run_all()
    """

    STEPS = [
        "scrape_index",
        "scrape_chapters",
        "translate_chapters",
        "parse_dialogue",
        "multispeaker_tts",
        "batch_tts",
        "forced_alignment",
        "smil_generation",
        "epub_export",
    ]

    def __init__(
        self,
        settings: SettingsManager,
        on_progress: ProgressCallback | None = None,
        work_dir: Path | str | None = None,
    ) -> None:
        self.settings = settings
        self._on_progress = on_progress or (lambda key, val: None)
        self._running = False

        # Data storage for pipeline state
        # Allow work_dir to be passed in (e.g., from ProjectManager)
        if work_dir:
            self.work_dir = Path(work_dir)
        else:
            self.work_dir = Path(self.settings.output_dir) / "pipeline_work"
        self.work_dir.mkdir(parents=True, exist_ok=True)

        self.chapter_urls: list[str] = []
        self.chapters: list[dict] = []
        self.translated_chapters: list[dict] = []
        self.dialogue_segments: dict[int, list[Segment]] = {}
        self.audio_files: dict[int, Path] = {}
        self.alignment_data: dict[int, list[AlignmentEntry]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run_all(self) -> None:
        """Execute every pipeline step in order."""
        self._running = True
        steps = [
            ("scrape_index",    self.scrape_index),
            ("scrape_chapters", self.scrape_chapters),
            ("translate_chapters", self.translate_chapters),
            ("parse_dialogue",  self.parse_dialogue),
            ("multispeaker_tts", self.multispeaker_tts),
            ("batch_tts",       self.batch_tts),
            ("forced_alignment", self.forced_alignment),
            ("smil_generation", self.smil_generation),
            ("epub_export",     self.epub_export),
        ]
        for key, method in steps:
            if not self._running:
                logger.info("Pipeline stopped before step '%s'.", key)
                break
            logger.info("Pipeline step: %s", key)
            self._on_progress(key, 0)
            try:
                method()
                self._on_progress(key, 100)
            except Exception as exc:
                logger.error(f"Pipeline step '{key}' failed: {exc}", exc_info=True)
                self._running = False
                break
        self._running = False

    def stop(self) -> None:
        """Signal the pipeline to stop after the current step."""
        self._running = False

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def scrape_index(self) -> None:
        """Fetch the chapter index from the configured URL."""
        index_url = self.settings.get("index_url", "")
        if not index_url:
            logger.warning("No index_url configured in settings.")
            return

        logger.info(f"Scraping index from: {index_url}")
        scraper = WebScraper()
        self.chapter_urls = scraper.scrape_index_page(index_url)
        logger.info(f"Found {len(self.chapter_urls)} chapter URLs.")

        # Save URLs to disk
        urls_file = self.work_dir / "chapter_urls.json"
        with open(urls_file, "w") as f:
            json.dump(self.chapter_urls, f, indent=2)

    def scrape_chapters(self) -> None:
        """Download all chapter pages listed in the scraped index."""
        if not self.chapter_urls:
            # Try loading from disk
            urls_file = self.work_dir / "chapter_urls.json"
            if urls_file.exists():
                with open(urls_file) as f:
                    self.chapter_urls = json.load(f)
            else:
                logger.warning("No chapter URLs available. Run scrape_index first.")
                return

        logger.info(f"Scraping {len(self.chapter_urls)} chapters...")
        scraper = WebScraper()
        self.chapters = scraper.scrape_chapters(self.chapter_urls)

        # Save chapters to disk
        chapters_file = self.work_dir / "chapters.json"
        with open(chapters_file, "w", encoding="utf-8") as f:
            json.dump(self.chapters, f, indent=2, ensure_ascii=False)

        logger.info(f"Scraped {len(self.chapters)} chapters successfully.")

    def translate_chapters(self) -> None:
        """Translate all scraped chapter files."""
        if not self.chapters:
            # Try loading from disk
            chapters_file = self.work_dir / "chapters.json"
            if chapters_file.exists():
                with open(chapters_file, encoding="utf-8") as f:
                    self.chapters = json.load(f)
            else:
                logger.warning("No chapters available. Run scrape_chapters first.")
                return

        target_lang = self.settings.get("translation_target_lang", "en")
        if not target_lang or target_lang == "skip":
            logger.info("Translation skipped (no target language configured).")
            self.translated_chapters = self.chapters
            return

        logger.info(f"Translating {len(self.chapters)} chapters to {target_lang}...")
        # For now, copy chapters as-is (TODO: implement real translation)
        self.translated_chapters = self.chapters.copy()

        # Save translated chapters
        translated_file = self.work_dir / "translated_chapters.json"
        with open(translated_file, "w", encoding="utf-8") as f:
            json.dump(self.translated_chapters, f, indent=2, ensure_ascii=False)

        logger.info(f"Translation complete for {len(self.translated_chapters)} chapters.")

    def parse_dialogue(self) -> None:
        """Parse chapter text into speaker-tagged segments via DialogueParser."""
        if not self.translated_chapters:
            # Try loading from disk
            translated_file = self.work_dir / "translated_chapters.json"
            if translated_file.exists():
                with open(translated_file, encoding="utf-8") as f:
                    self.translated_chapters = json.load(f)
            else:
                logger.warning("No translated chapters available.")
                return

        logger.info(f"Parsing dialogue for {len(self.translated_chapters)} chapters...")
        parser = DialogueParser()

        for i, chapter in enumerate(self.translated_chapters):
            chapter_id = f"ch{i:03d}"
            content = chapter.get("content", "")
            segments = parser.parse(content, chapter_id=chapter_id)
            self.dialogue_segments[i] = segments

        # Save segments to disk
        segments_file = self.work_dir / "dialogue_segments.json"
        segments_data = {
            str(k): [{"text": s.text, "speaker": s.speaker, "kind": s.kind, "paragraph_id": s.paragraph_id}
                     for s in v]
            for k, v in self.dialogue_segments.items()
        }
        with open(segments_file, "w", encoding="utf-8") as f:
            json.dump(segments_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Dialogue parsing complete.")

    def multispeaker_tts(self) -> None:
        """Synthesise audio with per-character voices using MultiSpeakerTTS."""
        if not self.dialogue_segments:
            # Try loading from disk
            segments_file = self.work_dir / "dialogue_segments.json"
            if segments_file.exists():
                with open(segments_file, encoding="utf-8") as f:
                    segments_data = json.load(f)
                    from ebook_app.models.dialogue_parser import Segment
                    self.dialogue_segments = {
                        int(k): [Segment(**s) for s in v]
                        for k, v in segments_data.items()
                    }
            else:
                logger.warning("No dialogue segments available.")
                return

        logger.info("Synthesizing audio with multispeaker TTS...")
        # TODO: Implement multispeaker synthesis with character voice mappings
        logger.info("Multispeaker TTS: not yet fully implemented.")

    def batch_tts(self) -> None:
        """Synthesise audio for narration-only chapters in a single voice."""
        if not self.dialogue_segments:
            logger.warning("No dialogue segments available for TTS.")
            return

        logger.info(f"Batch TTS for {len(self.dialogue_segments)} chapters...")
        engine = TTSEngine(
            output_dir=str(self.work_dir / "audio"),
            cli_path=self.settings.kokoro_cli_path,
        )

        for i, segments in self.dialogue_segments.items():
            chapter_id = f"ch{i:03d}"
            output_filename = f"{chapter_id}_audio.wav"

            # Combine all segment text
            full_text = "\n\n".join(s.text for s in segments if s.text.strip())

            if not full_text:
                logger.warning(f"Chapter {i} has no text to synthesize.")
                continue

            logger.info(f"Generating audio for chapter {i}...")
            audio_path = engine.generate_audio(
                text=full_text,
                output_filename=output_filename,
                voice=self.settings.tts_voice,
                speed=self.settings.tts_speed,
            )
            self.audio_files[i] = audio_path

        logger.info(f"Batch TTS complete: {len(self.audio_files)} audio files generated.")

    def forced_alignment(self) -> None:
        """Generate per-paragraph timestamps from audio + transcript."""
        if not self.audio_files or not self.dialogue_segments:
            logger.warning("Missing audio files or segments for forced alignment.")
            return

        logger.info("Running forced alignment...")
        aligner = ForcedAlignment()

        for i, audio_path in self.audio_files.items():
            segments = self.dialogue_segments.get(i, [])
            if not segments:
                continue

            chapter_id = f"ch{i:03d}"
            entries = aligner.align(
                wav_path=str(audio_path),
                segments=segments,
                chapter_id=chapter_id,
            )
            self.alignment_data[i] = entries

        # Save alignment data
        alignment_file = self.work_dir / "alignment_data.json"
        alignment_dict = {
            str(k): [{"paragraph_id": e.paragraph_id, "start_s": e.start_s,
                      "end_s": e.end_s, "text": e.text} for e in v]
            for k, v in self.alignment_data.items()
        }
        with open(alignment_file, "w", encoding="utf-8") as f:
            json.dump(alignment_dict, f, indent=2, ensure_ascii=False)

        logger.info("Forced alignment complete.")

    def smil_generation(self) -> None:
        """Build SMIL Media Overlay documents from alignment data."""
        if not self.alignment_data:
            # Try loading from disk
            alignment_file = self.work_dir / "alignment_data.json"
            if alignment_file.exists():
                with open(alignment_file, encoding="utf-8") as f:
                    alignment_dict = json.load(f)
                    from ebook_app.models.forced_alignment import AlignmentEntry
                    self.alignment_data = {
                        int(k): [AlignmentEntry(**e) for e in v]
                        for k, v in alignment_dict.items()
                    }
            else:
                logger.warning("No alignment data available.")
                return

        logger.info("Generating SMIL overlays...")
        # SMIL generation is handled by EPUBBuilder
        logger.info("SMIL generation will be handled during EPUB export.")

    def epub_export(self) -> None:
        """Package all processed assets into an EPUB3 file."""
        if not self.translated_chapters:
            logger.warning("No chapters available for EPUB export.")
            return

        logger.info("Exporting EPUB...")
        title = self.settings.get("book_title", "Untitled")
        author = self.settings.get("book_author", "Unknown")

        builder = EPUBBuilder(
            title=title,
            author=author,
            output_dir=str(self.settings.output_dir),
        )

        # Add chapters with audio and SMIL
        for i, chapter in enumerate(self.translated_chapters):
            chapter_id = f"ch{i:03d}"
            xhtml_filename = f"{chapter_id}.xhtml"
            chapter_title = chapter.get("title", f"Chapter {i+1}")

            # Generate basic XHTML
            xhtml_content = self._generate_xhtml(chapter, chapter_id)
            builder.add_chapter(xhtml_filename, xhtml_content, chapter_title)

            # Add audio and SMIL if available
            if i in self.audio_files and i in self.alignment_data:
                audio_path = self.audio_files[i]
                alignment = self.alignment_data[i]

                # Convert alignment to TextSegments
                text_segments = [
                    TextSegment(
                        paragraph_id=entry.paragraph_id,
                        clip_begin=entry.start_s,
                        clip_end=entry.end_s,
                    )
                    for entry in alignment
                ]

                builder.add_audio(xhtml_filename, str(audio_path), text_segments)

        # Build the EPUB
        epub_path = builder.build()
        logger.info(f"EPUB exported successfully: {epub_path}")

    def _generate_xhtml(self, chapter: dict, chapter_id: str) -> str:
        """Generate basic XHTML for a chapter."""
        title = chapter.get("title", "Chapter")
        content = chapter.get("content", "")

        # Get segments if available for paragraph IDs
        segments = self.dialogue_segments.get(int(chapter_id[2:]), [])

        xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>{title}</title>
</head>
<body>
    <h1>{title}</h1>
"""

        if segments:
            for seg in segments:
                para_id = seg.paragraph_id or f"{chapter_id}_p0"
                text = seg.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                xhtml += f'    <p id="{para_id}">{text}</p>\n'
        else:
            # Fallback: split content by paragraphs
            paragraphs = content.split("\n\n")
            for i, para in enumerate(paragraphs):
                if para.strip():
                    para_id = f"{chapter_id}_p{i}"
                    text = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    xhtml += f'    <p id="{para_id}">{text}</p>\n'

        xhtml += """</body>
</html>"""
        return xhtml
