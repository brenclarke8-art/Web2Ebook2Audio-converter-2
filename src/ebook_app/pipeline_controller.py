# src/ebook_app/pipeline_controller.py
"""Pipeline orchestration controller — runs the end-to-end processing pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from ebook_app.models.book_library import FillerChapterFilter
from ebook_app.models.dialogue_parser import DialogueParser, Segment
from ebook_app.models.epub_builder import EPUBBuilder
from ebook_app.models.forced_alignment import ForcedAlignment, AlignmentEntry
from ebook_app.models.media_overlay import MediaOverlayBuilder, TextSegment
from ebook_app.models.scraper import WebScraper

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ebook_app.core.settings_manager import SettingsManager

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
        self.raw_chapter_urls: list[str] = []
        self.chapters: list[dict] = []
        self.translated_chapters: list[dict] = []
        self.dialogue_segments: dict[int, list[Segment]] = {}
        self.audio_files: dict[int, Path] = {}
        self.alignment_data: dict[int, list[AlignmentEntry]] = {}
        self.selected_start_chapter: int = 1
        self.selected_end_chapter: int = 0
        self.review_required: bool = False

    @staticmethod
    def _normalize_name(name: str) -> str:
        return " ".join((name or "").strip().lower().split())

    @staticmethod
    def _segment_to_dict(segment: Segment) -> dict:
        return {
            "text": segment.text,
            "type": segment.type,
            "speaker": segment.speaker,
            "gender": segment.gender,
            "speaker_confidence": segment.speaker_confidence,
            "gender_confidence": segment.gender_confidence,
            "character_confidence": segment.character_confidence,
            "paragraph_id": segment.paragraph_id,
        }

    # ------------------------------------------------------------------
    # TTS backend factory
    # ------------------------------------------------------------------

    def _make_tts_backend(self, output_dir: str | None = None):
        """Return a TTSEngine (local) or TTSClient (remote) per settings."""
        effective_output_dir = output_dir or str(self.work_dir / "audio")
        if self.settings.tts_backend_mode == "remote":
            from ebook_app.services.tts_client import TTSClient

            return TTSClient(
                output_dir=effective_output_dir,
                base_url=self.settings.tts_backend_url,
            )
        from ebook_app.models.tts_engine_cli import TTSEngine

        return TTSEngine(
            output_dir=effective_output_dir,
            model_path=self.settings.kokoro_model_path or None,
            voices_path=self.settings.kokoro_voices_path or None,
        )

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
            if key in {"multispeaker_tts", "batch_tts", "forced_alignment", "smil_generation", "epub_export"}:
                review_approved = bool(self.settings.get("character_review_approved", False))
                if not review_approved:
                    self.review_required = True
                    logger.info(
                        "Pipeline paused before '%s': character review approval required.",
                        key,
                    )
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

    def set_chapter_range(self, start_chapter: int, end_chapter: int) -> None:
        """Set the 1-based chapter range to process."""
        start = max(1, int(start_chapter))
        end = max(start, int(end_chapter))
        self.selected_start_chapter = start
        self.selected_end_chapter = end
        with open(self.work_dir / "selected_range.json", "w", encoding="utf-8") as f:
            json.dump({"start": start, "end": end}, f, indent=2, ensure_ascii=False)

    def get_chapter_inventory(self) -> dict:
        """Return chapter inventory for current index scrape state."""
        return {
            "raw_count": len(self.raw_chapter_urls),
            "valid_count": len(self.chapter_urls),
        }

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
        self.raw_chapter_urls = scraper.scrape_index_page(index_url)
        url_filter = FillerChapterFilter()
        self.chapter_urls, filtered_urls = url_filter.filter_urls(self.raw_chapter_urls)
        logger.info(
            "Found %d chapter URLs (%d valid, %d filtered).",
            len(self.raw_chapter_urls),
            len(self.chapter_urls),
            len(filtered_urls),
        )

        # Save URLs to disk
        raw_urls_file = self.work_dir / "raw_chapter_urls.json"
        with open(raw_urls_file, "w", encoding="utf-8") as f:
            json.dump(self.raw_chapter_urls, f, indent=2, ensure_ascii=False)

        urls_file = self.work_dir / "chapter_urls.json"
        with open(urls_file, "w", encoding="utf-8") as f:
            json.dump(self.chapter_urls, f, indent=2, ensure_ascii=False)

    def scrape_chapters(self) -> None:
        """Download all chapter pages listed in the scraped index."""
        if not self.chapter_urls:
            # Try loading from disk
            urls_file = self.work_dir / "chapter_urls.json"
            if urls_file.exists():
                with open(urls_file, encoding="utf-8") as f:
                    self.chapter_urls = json.load(f)
            else:
                logger.warning("No chapter URLs available. Run scrape_index first.")
                return

        if self.selected_end_chapter <= 0:
            self.selected_end_chapter = len(self.chapter_urls)
        start_idx = max(0, self.selected_start_chapter - 1)
        end_idx = min(len(self.chapter_urls), self.selected_end_chapter)
        selected_urls = self.chapter_urls[start_idx:end_idx]
        if not selected_urls:
            logger.warning(
                "No chapters selected for range %d-%d.",
                self.selected_start_chapter,
                self.selected_end_chapter,
            )
            return

        logger.info(
            "Scraping chapters %d-%d (%d chapters).",
            self.selected_start_chapter,
            self.selected_end_chapter,
            len(selected_urls),
        )
        scraper = WebScraper()
        self.chapters = scraper.scrape_chapters(selected_urls)

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
        translated_file = self.work_dir / "translated_chapters.json"
        self.translated_chapters = []
        total = len(self.chapters)
        for idx, chapter in enumerate(self.chapters, start=1):
            # For now, copy chapters as-is (TODO: implement real translation)
            self.translated_chapters.append(chapter.copy())
            with open(translated_file, "w", encoding="utf-8") as f:
                json.dump(self.translated_chapters, f, indent=2, ensure_ascii=False)
            self._on_progress("translate_chapters", int(idx * 100 / max(total, 1)))

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

        logger.info("Parsing dialogue for %d chapters...", len(self.translated_chapters))
        parser = DialogueParser(
            ollama_url=self.settings.get("ollama_url", ""),
            model=self.settings.get("ollama_model", ""),
        )

        known_characters = self.settings.get("character_db", []) or []
        known_names = {
            self._normalize_name(item.get("name", ""))
            for item in known_characters
            if item.get("name")
        }
        pending = self.settings.get("pending_character_additions", []) or []
        pending_names = {
            self._normalize_name(item.get("name", ""))
            for item in pending
            if item.get("name")
        }
        threshold = float(self.settings.get("character_confidence_threshold", 0.8))

        aggregated: dict[str, dict] = {}

        total = len(self.translated_chapters)
        for i, chapter in enumerate(self.translated_chapters):
            chapter_id = f"ch{i:03d}"
            content = chapter.get("content", "")
            parse_result = parser.parse(content, chapter_id=chapter_id)
            self.dialogue_segments[i] = parse_result.segments

            chapter_info = {
                "chapter_index": i,
                "chapter_id": chapter_id,
                "title": chapter.get("title", f"Chapter {i + 1}"),
                "segments": [self._segment_to_dict(s) for s in parse_result.segments],
                "detected_characters": [
                    {"name": c.name, "gender": c.gender, "confidence": c.confidence}
                    for c in parse_result.detected_characters
                ],
            }
            aggregated[str(i)] = chapter_info
            chapter_dir = self.work_dir / chapter_id
            chapter_dir.mkdir(parents=True, exist_ok=True)
            with open(chapter_dir / "chapter_info.json", "w", encoding="utf-8") as f:
                json.dump(chapter_info, f, indent=2, ensure_ascii=False)

            for detected in parse_result.detected_characters:
                normalized = self._normalize_name(detected.name)
                if (
                    normalized
                    and detected.confidence >= threshold
                    and normalized not in known_names
                    and normalized not in pending_names
                ):
                    pending.append(
                        {
                            "name": detected.name,
                            "gender": detected.gender,
                            "confidence": detected.confidence,
                            "source_chapter": chapter_id,
                        }
                    )
                    pending_names.add(normalized)

            self._on_progress("parse_dialogue", int((i + 1) * 100 / max(total, 1)))

        # Save segments to disk
        segments_file = self.work_dir / "dialogue_segments.json"
        segments_data = {
            str(k): [self._segment_to_dict(s)
                     for s in v]
            for k, v in self.dialogue_segments.items()
        }
        with open(segments_file, "w", encoding="utf-8") as f:
            json.dump(segments_data, f, indent=2, ensure_ascii=False)

        chapter_info_file = self.work_dir / "chapter_info.json"
        with open(chapter_info_file, "w", encoding="utf-8") as f:
            json.dump(aggregated, f, indent=2, ensure_ascii=False)

        self.settings.set("pending_character_additions", pending)
        self.settings.set("character_review_approved", False)
        self.review_required = True

        logger.info("Dialogue parsing complete.")

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
                        int(k): [
                            Segment(
                                text=s.get("text", ""),
                                type=s.get("type", s.get("kind", "narration")),
                                speaker=s.get("speaker", "narrator"),
                                gender=s.get("gender", "unknown"),
                                speaker_confidence=float(s.get("speaker_confidence", 0.0)),
                                gender_confidence=float(s.get("gender_confidence", 0.0)),
                                character_confidence=float(s.get("character_confidence", 0.0)),
                                paragraph_id=s.get("paragraph_id", ""),
                            )
                            for s in v
                        ]
                        for k, v in segments_data.items()
                    }
            else:
                logger.warning("No dialogue segments available.")
                return

        if not self.settings.get("multispeaker_enabled", False):
            logger.info("Multispeaker mode disabled; skipping multispeaker_tts step.")
            return

        logger.info("Synthesizing audio with multispeaker TTS...")
        engine = self._make_tts_backend(output_dir=str(self.work_dir / "audio"))

        narrator_voice = self.settings.get("narrator_voice", "af_heart")
        default_male_voice = self.settings.get("default_male_voice", "am_adam")
        default_female_voice = self.settings.get("default_female_voice", "af_heart")

        voice_mappings = {"narrator": narrator_voice}
        for item in self.settings.get("character_db", []) or []:
            name = (item.get("name") or "").strip()
            voice = (item.get("voice") or "").strip()
            if name and voice:
                voice_mappings[name] = voice

        audio_mode = self.settings.get("audio_output_mode", "per_chapter")
        if audio_mode == "single_file":
            full_segments: list[Segment] = []
            for _, segments in sorted(self.dialogue_segments.items()):
                full_segments.extend(segments)
            if not full_segments:
                logger.warning("No dialogue segments available for combined audio.")
                return
            output_filename = "book_audio.wav"
            audio_path = engine.generate_multi_voice_audio(
                dialogue_segments=full_segments,
                output_filename=output_filename,
                voice_mappings=voice_mappings,
                default_male_voice=default_male_voice,
                default_female_voice=default_female_voice,
                speed=self.settings.tts_speed,
            )
            self.audio_files = {0: audio_path}
            logger.info("Multispeaker TTS complete: generated combined book audio.")
            return

        for i, segments in self.dialogue_segments.items():
            chapter_id = f"ch{i:03d}"
            output_filename = f"{chapter_id}_audio.wav"
            try:
                audio_path = engine.generate_multi_voice_audio(
                    dialogue_segments=segments,
                    output_filename=output_filename,
                    voice_mappings=voice_mappings,
                    default_male_voice=default_male_voice,
                    default_female_voice=default_female_voice,
                    speed=self.settings.tts_speed,
                )
                self.audio_files[i] = audio_path
            except Exception as exc:
                logger.error("Multispeaker TTS failed for %s: %s", chapter_id, exc)

        logger.info("Multispeaker TTS complete: %d audio files generated.", len(self.audio_files))

    def batch_tts(self) -> None:
        """Synthesise audio for narration-only chapters in a single voice."""
        if not self.dialogue_segments:
            logger.warning("No dialogue segments available for TTS.")
            return

        logger.info(f"Batch TTS for {len(self.dialogue_segments)} chapters...")
        engine = self._make_tts_backend(output_dir=str(self.work_dir / "audio"))
        audio_mode = self.settings.get("audio_output_mode", "per_chapter")

        if audio_mode == "single_file":
            full_text_parts: list[str] = []
            for _, segments in sorted(self.dialogue_segments.items()):
                full_text_parts.extend(s.text for s in segments if s.text.strip())
            full_text = "\n\n".join(full_text_parts).strip()
            if not full_text:
                logger.warning("No text available to synthesize combined audio.")
                return
            audio_path = engine.generate_audio(
                text=full_text,
                output_filename="book_audio.wav",
                voice=self.settings.tts_voice,
                speed=self.settings.tts_speed,
            )
            self.audio_files = {0: audio_path}
            logger.info("Batch TTS complete: generated combined book audio.")
            return

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
        audio_mode = self.settings.get("audio_output_mode", "per_chapter")

        for i, audio_path in self.audio_files.items():
            if audio_mode == "single_file":
                segments = []
                for _, chapter_segments in sorted(self.dialogue_segments.items()):
                    segments.extend(chapter_segments)
            else:
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
        audio_mode = self.settings.get("audio_output_mode", "per_chapter")

        # Add chapters with audio and SMIL
        for i, chapter in enumerate(self.translated_chapters):
            chapter_id = f"ch{i:03d}"
            xhtml_filename = f"{chapter_id}.xhtml"
            chapter_title = chapter.get("title", f"Chapter {i+1}")

            # Generate basic XHTML
            xhtml_content = self._generate_xhtml(chapter, chapter_id)
            builder.add_chapter(xhtml_filename, xhtml_content, chapter_title)

            # Add audio and SMIL if available
            if audio_mode == "single_file":
                continue
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
