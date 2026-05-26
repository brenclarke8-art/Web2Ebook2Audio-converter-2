# src/ebook_app/pipeline_controller.py
"""Pipeline orchestration controller — runs the end-to-end processing pipeline."""

from __future__ import annotations

import logging
from typing import Callable

from ebook_app.core.settings_manager import SettingsManager

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

    TODO: each stub method should instantiate the corresponding service,
    start its QThread, and await completion before proceeding to the next step.
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
    ) -> None:
        self.settings = settings
        self._on_progress = on_progress or (lambda key, val: None)
        self._running = False

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
            method()
            self._on_progress(key, 100)
        self._running = False

    def stop(self) -> None:
        """Signal the pipeline to stop after the current step."""
        self._running = False

    # ------------------------------------------------------------------
    # Pipeline steps — stubs
    # ------------------------------------------------------------------

    def scrape_index(self) -> None:
        """Fetch the chapter index from the configured URL.

        TODO: instantiate ScrapingService, run scrape_index(), await result.
        """
        logger.info("scrape_index: not yet implemented.")

    def scrape_chapters(self) -> None:
        """Download all chapter pages listed in the scraped index.

        TODO: continue ScrapingService with chapter URLs.
        """
        logger.info("scrape_chapters: not yet implemented.")

    def translate_chapters(self) -> None:
        """Translate all scraped chapter files.

        TODO: instantiate TranslationService and await result.
        """
        logger.info("translate_chapters: not yet implemented.")

    def parse_dialogue(self) -> None:
        """Parse chapter text into speaker-tagged segments via DialogueParser.

        TODO: iterate chapters, call DialogueParser.parse(), save JSON.
        """
        logger.info("parse_dialogue: not yet implemented.")

    def multispeaker_tts(self) -> None:
        """Synthesise audio with per-character voices using MultiSpeakerTTS.

        TODO: load segments, call MultiSpeakerTTS.synthesise_segments().
        """
        logger.info("multispeaker_tts: not yet implemented.")

    def batch_tts(self) -> None:
        """Synthesise audio for narration-only chapters in a single voice.

        TODO: start TTSService for remaining non-dialogue chapters.
        """
        logger.info("batch_tts: not yet implemented.")

    def forced_alignment(self) -> None:
        """Generate per-paragraph timestamps from audio + transcript.

        TODO: call ForcedAlignment.align() for each chapter WAV.
        """
        logger.info("forced_alignment: not yet implemented.")

    def smil_generation(self) -> None:
        """Build SMIL Media Overlay documents from alignment data.

        TODO: call media_overlay.build_smil() for each chapter.
        """
        logger.info("smil_generation: not yet implemented.")

    def epub_export(self) -> None:
        """Package all processed assets into an EPUB3 file.

        TODO: instantiate EPUBService and await result.
        """
        logger.info("epub_export: not yet implemented.")
