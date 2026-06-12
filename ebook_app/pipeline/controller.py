# ebook_app/pipeline/controller.py
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from ebook_app.app.state.character_db import CharacterDatabase
from ebook_app.text.identify.role_tagger import Pass1Extractor
from ebook_app.text.identify.type_classifier import Pass2Classifier, LLMClient
from ebook_app.tts.voice_router import VoiceRouter
from ebook_app.pipeline.chapter_rebuilder import ChapterRebuilder
from ebook_app.epub.packaging import EPUBBuilder
from ebook_app.tts.tts_service import TTSEngineContract

logger = logging.getLogger(__name__)


class PipelineSettings:
    """
    Minimal settings container used by PipelineController.
    Extend as needed.
    """

    def __init__(
        self,
        work_dir: Path,
        output_dir: Path,
        book_title: str = "Untitled Book",
        book_author: str = "Unknown Author",
        tts_speed: float = 1.0,
        narrator_voice: str = "af_narrator",
        default_male_voice: str = "af_male",
        default_female_voice: str = "af_female",
        llm_base_url: str = "",
        llm_model: str = "",
        index_url: str = "",
    ) -> None:
        self.work_dir = work_dir
        self.output_dir = output_dir
        self.book_title = book_title
        self.book_author = book_author
        self.tts_speed = tts_speed
        self.narrator_voice = narrator_voice
        self.default_male_voice = default_male_voice
        self.default_female_voice = default_female_voice
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model
        self.index_url = index_url


class PipelineController:
    """
    Unified controller for the 7‑phase hybrid pipeline:

        1. scrape_index
        2. scrape_chapters
        3. pass1_extraction
        4. pass2_classification
        5. smart_review_dialogue (rebuild final chapters)
        6. tts_generate
        7. epub_build
    """

    def __init__(self, settings: PipelineSettings) -> None:
        self.settings = settings
        self.work_dir: Path = settings.work_dir
        self.selected_start_chapter: int = 1

        self.character_db = CharacterDatabase(
            path=self.work_dir / "character_database.json"
        )



        # Voice routing + chapter rebuild helpers
        self.voice_router = VoiceRouter(
            narrator_voice=settings.narrator_voice,
            default_male_voice=settings.default_male_voice,
            default_female_voice=settings.default_female_voice,
        )
        self.chapter_rebuilder = ChapterRebuilder(self.voice_router)

        # LLM client + Pass‑2 classifier
        self.llm_client = LLMClient(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
        self.pass2_classifier = Pass2Classifier(self.llm_client)

        # Cancellation + progress callbacks
        self._cancel_flags: Dict[str, bool] = {}
        self._progress_callback = None

    # ------------------------------------------------------------------
    # Helpers: JSON I/O, paths, progress, cancellation
    # ------------------------------------------------------------------

    def _load_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.error("Failed to load JSON from %s", path, exc_info=True)
            return default

    def _save_json(self, path: Path, data: Any) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.error("Failed to save JSON to %s", path, exc_info=True)

    def _chapter_id_for_offset(self, offset: int) -> str:
        return f"ch{offset + 1:03d}"

    def _chapter_cleaned_text_path(self, chapter_id: str) -> Path:
        return self.work_dir / f"{chapter_id}_cleaned.txt"

    def _chapter_pass1_path(self, chapter_id: str) -> Path:
        return self.work_dir / f"{chapter_id}_pass1.json"

    def _chapter_pass2_path(self, chapter_id: str) -> Path:
        return self.work_dir / f"{chapter_id}_pass2.json"

    def _chapter_final_path(self, chapter_id: str) -> Path:
        return self.work_dir / f"{chapter_id}_final.json"

    def _on_progress(self, phase: str, percent: int) -> None:
        if self._progress_callback:
            try:
                self._progress_callback(phase, percent)
            except Exception:
                logger.debug("Progress callback failed for %s", phase, exc_info=True)

    def _cancelled(self, phase: str) -> bool:
        return bool(self._cancel_flags.get(phase, False))

    def request_cancel(self, phase: str) -> None:
        self._cancel_flags[phase] = True

    def set_progress_callback(self, cb) -> None:
        self._progress_callback = cb

    # ------------------------------------------------------------------
    # Phase 1 — scrape_index (web scraping to get chapter list)
    # ------------------------------------------------------------------

    def scrape_index(self) -> None:
        """
        Phase 1:
        - Scrape the chapter index using WebScraper
        - Write chapters_raw.json with a list of chapter metadata
        """
        logger.info("[Phase 1] Scraping index…")

        from ebook_app.text.scrape.browser_scraper import WebScraper

        index_url = self.settings.index_url or ""
        if not index_url:
            logger.warning("No index URL configured — cannot scrape index.")
            self._on_progress("scrape_index", 100)
            return

        scraper = WebScraper()
        try:
            chapters = list(scraper.scrape_index_page(index_url))
        except Exception:
            logger.error("Index scraping failed.", exc_info=True)
            chapters = []

        # Normalize into a list of dicts
        normalized = []
        for idx, url in enumerate(chapters):
            normalized.append({
                "title": f"Chapter {idx + 1}",
                "source": str(url),
            })

        out_path = self.work_dir / "chapters_raw.json"
        self._save_json(out_path, normalized)

        logger.info("Index scraped: %d chapters.", len(normalized))
        self._on_progress("scrape_index", 100)


    # ------------------------------------------------------------------
    # Phase 2 — scrape_chapters (per-chapter scraping + cleaning)
    # ------------------------------------------------------------------

    def scrape_chapters(self) -> None:
        """
        Phase 2:
        - Scrape each chapter's raw text
        - Clean it using TextCleaner
        - Write chXXX_cleaned.txt
        """
        logger.info("[Phase 2] Scraping chapters…")

        from ebook_app.text.scrape.browser_scraper import WebScraper
        from ebook_app.text.parse.html_cleaner import TextCleaner

        chapters = self._load_json(self.work_dir / "chapters_raw.json", default=[])
        total = len(chapters)
        if total == 0:
            logger.warning("No chapters_raw.json found — cannot scrape chapters.")
            return

        scraper = WebScraper()

        for idx, ch in enumerate(chapters):
            if self._cancelled("scrape_chapters"):
                return

            chapter_id = self._chapter_id_for_offset(idx)
            cleaned_path = self._chapter_cleaned_text_path(chapter_id)

            url = ch.get("source", "")
            if not url:
                logger.warning("Chapter %s has no source URL.", chapter_id)
                continue

            try:
                results = scraper.scrape_chapters([url])
                raw_text = results[0].get("content", "") if results else ""
                if not raw_text:
                    logger.warning("Scraper returned empty content for %s", url)
            except Exception:
                logger.error("Failed to scrape %s", url, exc_info=True)
                raw_text = ""

            cleaned = TextCleaner.clean_text(raw_text or "")
            cleaned_path.write_text(cleaned, encoding="utf-8")

            logger.info("Scraped + cleaned %s", chapter_id)

            percent = int((idx + 1) * 100 / total)
            self._on_progress("scrape_chapters", percent)

        logger.info("Phase 2 — scrape_chapters complete.")
        self._on_progress("scrape_chapters", 100)

    # ------------------------------------------------------------------
    # Phase 3 — pass1_extraction (deterministic, no LLM)
    # ------------------------------------------------------------------

    def pass1_extraction(self) -> None:
        """
        Phase 3:
        - Read chXXX_cleaned.txt
        - Run Pass‑1 extractor (deterministic, no LLM)
        - Write chXXX_pass1.json
        """
        logger.info("[Phase 3] Pass‑1 extraction…")

        chapters = self._load_json(self.work_dir / "chapters_raw.json", default=[])
        total = len(chapters)
        if total == 0:
            logger.warning("No chapters_raw.json found — cannot run Pass‑1.")
            return

        extractor = Pass1Extractor()

        for idx in range(total):
            if self._cancelled("pass1_extraction"):
                return

            chapter_id = self._chapter_id_for_offset(idx)
            cleaned_path = self._chapter_cleaned_text_path(chapter_id)

            if not cleaned_path.exists():
                logger.warning("Missing cleaned text for %s — skipping Pass‑1.", chapter_id)
                continue

            text = cleaned_path.read_text(encoding="utf-8")
            segments = extractor.extract(text=text, chapter_id=chapter_id)

            out_path = self._chapter_pass1_path(chapter_id)
            self._save_json(out_path, {"chapter_id": chapter_id, "segments": segments})

            logger.info(
                "Pass‑1 extracted %d segments for %s (%d/%d).",
                len(segments),
                chapter_id,
                idx + 1,
                total,
            )

            percent = int((idx + 1) * 100 / total)
            self._on_progress("pass1_extraction", percent)

        logger.info("Phase 3 — Pass‑1 extraction complete.")
        self._on_progress("pass1_extraction", 100)

    # ------------------------------------------------------------------
    # Phase 4 — pass2_classification (LLM-based)
    # ------------------------------------------------------------------

    def pass2_classification(self) -> None:
        """
        Phase 4:
        - Read chXXX_pass1.json
        - Run Pass‑2 classifier (LLM-based)
        - Write chXXX_pass2.json
        """
        logger.info("[Phase 4] Pass‑2 classification…")

        chapters = self._load_json(self.work_dir / "chapters_raw.json", default=[])
        total = len(chapters)
        if total == 0:
            logger.warning("No chapters_raw.json found — cannot run Pass‑2.")
            return

        for idx in range(total):
            if self._cancelled("pass2_classification"):
                return

            chapter_id = self._chapter_id_for_offset(idx)
            pass1_path = self._chapter_pass1_path(chapter_id)

            if not pass1_path.exists():
                logger.warning("Missing Pass‑1 output for %s — skipping Pass‑2.", chapter_id)
                continue

            data = self._load_json(pass1_path, default={})
            segments = data.get("segments", [])
            if not segments:
                logger.warning("No Pass‑1 segments in %s — skipping.", pass1_path)
                continue

            classified = []
            for seg_idx, seg in enumerate(segments):
                if self._cancelled("pass2_classification"):
                    return

                try:
                    result = self.pass2_classifier.classify_segment(seg)
                    merged = {**seg, **result}
                except Exception:
                    logger.error(
                        "Pass‑2 classification failed for %s segment %d",
                        chapter_id,
                        seg_idx,
                        exc_info=True,
                    )
                    merged = {
                        **seg,
                        "type": "narration",
                        "speaker": "unknown",
                        "gender": "unknown",
                        "confidence": 0.0,
                    }

                classified.append(merged)



            out_path = self._chapter_pass2_path(chapter_id)
            self._save_json(out_path, {"chapter_id": chapter_id, "segments": classified})

            logger.info(
                "Pass‑2 classified %d segments for %s (%d/%d).",
                len(classified),
                chapter_id,
                idx + 1,
                total,
            )

            percent = int((idx + 1) * 100 / total)
            self._on_progress("pass2_classification", percent)

        logger.info("Phase 4 — Pass‑2 classification complete.")
        self._on_progress("pass2_classification", 100)

    # ------------------------------------------------------------------
    # Phase 5 — smart_review_dialogue (rebuild final chapters)
    # ------------------------------------------------------------------

    def smart_review_dialogue(self) -> None:
        logger.info("[Phase 5] Smart review + chapter rebuild…")

        chapters = self._load_json(self.work_dir / "chapters_raw.json", default=[])
        total = len(chapters)
        if total == 0:
            logger.warning("No chapters_raw.json found — cannot rebuild chapters.")
            return

        for idx, ch_entry in enumerate(chapters):
            if self._cancelled("smart_review_dialogue"):
                return

            chapter_id = self._chapter_id_for_offset(idx)
            pass2_path = self._chapter_pass2_path(chapter_id)

            if not pass2_path.exists():
                logger.warning("Missing Pass‑2 output for %s — skipping rebuild.", chapter_id)
                continue

            data = self._load_json(pass2_path, default={})
            segments = data.get("segments", [])
            if not segments:
                logger.warning("No Pass‑2 segments in %s — skipping.", pass2_path)
                continue

            title = str(ch_entry.get("title", "") or f"Chapter {idx + 1}")

            final_chapter = self.chapter_rebuilder.rebuild_chapter(
                chapter_id=chapter_id,
                title=title,
                pass2_segments=segments,
                character_db=self.character_db,   # CharacterDatabase instance
            )

            out_path = self._chapter_final_path(chapter_id)
            self._save_json(out_path, final_chapter)

            percent = int((idx + 1) * 100 / total)
            self._on_progress("smart_review_dialogue", percent)

        # NEW: persist character DB
        if hasattr(self.character_db, "save"):
            self.character_db.save()

        logger.info("Phase 5 — smart_review_dialogue complete.")
        self._on_progress("smart_review_dialogue", 100)

    # ------------------------------------------------------------------
    # Phase 6 — TTS generation (per-segment, per-chapter)
    # ------------------------------------------------------------------

    def _make_tts_backend(self, output_dir: str) -> TTSEngineContract:
        """
        Build a TTS backend instance.
        This must be implemented to return an object that satisfies TTSEngineContract.
        """
        raise NotImplementedError("_make_tts_backend must be implemented.")

    def tts_generate(self) -> None:
        """
        Phase 6:
        - Read chXXX_final.json
        - Generate per-segment WAVs: audio/chXXX/chXXX_segYYY.wav
        - Concatenate per-chapter WAV: audio/chXXX/chXXX.wav
        - Write audio_timing.json
        """
        logger.info("[Phase 6] Generating TTS audio…")

        chapters = self._load_json(self.work_dir / "chapters_raw.json", default=[])
        total = len(chapters)
        if total == 0:
            logger.warning("No chapters_raw.json found — skipping TTS generation.")
            return

        audio_root = self.work_dir / "audio"
        audio_root.mkdir(parents=True, exist_ok=True)
        engine = self._make_tts_backend(output_dir=str(audio_root))

        audio_timing: Dict[str, List[Dict]] = {}
        tts_speed = float(self.settings.tts_speed or 1.0)

        for idx in range(total):
            if self._cancelled("tts_generate"):
                return

            chapter_id = self._chapter_id_for_offset(idx)
            final_info_path = self._chapter_final_path(chapter_id)

            if not final_info_path.exists():
                logger.warning(
                    "Missing final chapter info for %s — skipping TTS.",
                    chapter_id,
                )
                continue

            data = self._load_json(final_info_path, default={})
            segments = data.get("segments", [])
            if not segments:
                logger.warning("No segments in %s — skipping.", final_info_path)
                continue

            logger.info("Generating audio for %s (%d/%d)…", chapter_id, idx + 1, total)

            chapter_audio_dir = audio_root / chapter_id
            chapter_audio_dir.mkdir(parents=True, exist_ok=True)

            segment_files: List[str] = []
            timing_entries: List[Dict] = []
            current_time = 0.0

            for seg_idx, seg in enumerate(segments):
                if self._cancelled("tts_generate"):
                    return

                text = str(seg.get("text", "") or "").strip()
                if not text:
                    continue

                voice = seg.get("voice") or self.voice_router.get_voice_for_segment(seg, self.character_db)


                seg_filename = f"{chapter_id}_seg{seg_idx:03d}.wav"
                seg_path = chapter_audio_dir / seg_filename

                try:
                    engine.generate_audio(
                        text=text,
                        output_filename=str(seg_path),
                        voice=voice,
                        speed=tts_speed,
                    )
                    if self._cancelled("tts_generate"):
                        return
                    duration = float(engine.get_last_audio_duration() or 0.0)
                except Exception:
                    logger.error(
                        "TTS generation failed for %s segment %d",
                        chapter_id,
                        seg_idx,
                        exc_info=True,
                    )
                    continue

                paragraph_id = seg.get("paragraph_id", f"{chapter_id}_p{seg_idx}")
                timing_entries.append(
                    {
                        "paragraph_id": paragraph_id,
                        "clip_begin": current_time,
                        "clip_end": current_time + duration,
                    }
                )
                current_time += duration
                segment_files.append(str(seg_path))

            if not segment_files:
                logger.warning("No audio segments generated for %s — skipping concat.", chapter_id)
                continue

            chapter_wav = chapter_audio_dir / f"{chapter_id}.wav"
            try:
                engine.concatenate_audio_files(segment_files, chapter_wav)
            except Exception:
                logger.error(
                    "Failed to concatenate audio for %s",
                    chapter_id,
                    exc_info=True,
                )
                continue

            audio_timing[chapter_id] = timing_entries

            percent = int((idx + 1) * 100 / total)
            self._on_progress("tts_generate", percent)

        timing_path = self.work_dir / "audio_timing.json"
        self._save_json(timing_path, audio_timing)

        logger.info(
            "Phase 6 — TTS generation complete. %d chapters with timing data.",
            len(audio_timing),
        )

    # ------------------------------------------------------------------
    # TTS Preview — segment-level
    # ------------------------------------------------------------------

    def tts_generate_segment(
        self,
        chapter_index: int,
        segment_index: int,
    ) -> Path:
        """
        Generate TTS audio for a single semantic segment (preview).
        Uses the same multi-speaker logic as full TTS.
        """
        chapter_id = self._chapter_id_for_offset(chapter_index)
        info_file = self._chapter_final_path(chapter_id)

        if not info_file.exists():
            raise FileNotFoundError(f"final chapter JSON not found for {chapter_id}")

        data = self._load_json(info_file, default={})
        segments = data.get("segments", [])

        if not (0 <= segment_index < len(segments)):
            raise IndexError(
                f"Segment index {segment_index} out of range for {chapter_id} "
                f"(have {len(segments)} segments)"
            )

        seg = segments[segment_index]
        text = (seg.get("text") or "").strip()
        if not text:
            raise ValueError(f"Segment {segment_index} in {chapter_id} has empty text")

        voice_name = self.voice_router.get_voice_for_segment(seg, self.character_db)

        preview_dir = self.work_dir / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)

        # Use stable segment_id
        seg_id = seg.get("segment_id", f"{chapter_id}_s{segment_index:03d}")
        out_path = preview_dir / f"{seg_id}_preview.wav"

        engine = self._make_tts_backend(output_dir=str(preview_dir))

        logger.info(
            "TTS segment preview: chapter=%s, segment=%d, speaker=%s, type=%s, voice=%s",
            chapter_id,
            segment_index,
            seg.get("speaker", "narrator"),
            seg.get("type", "narration"),
            voice_name,
        )

        engine.generate_audio(
            text=text,
            output_filename=str(out_path),
            voice=voice_name,
            speed=self.settings.tts_speed,
        )

        return out_path

    # ------------------------------------------------------------------
    # Phase 7 — EPUB build (EPUB3 + SMIL)
    # ------------------------------------------------------------------

    def epub_build(self) -> None:
        """
        Phase 7:
        - Load final chapter info (chXXX_final.json)
        - Load audio_timing.json
        - Build per-chapter XHTML with <p id=paragraph_id>
        - Attach audio + timing via EPUBBuilder.add_audio()
        - Build final EPUB via EPUBBuilder.build()
        """
        logger.info("[Phase 7] Building EPUB…")

        chapters = self._load_json(self.work_dir / "chapters_raw.json", default=[])
        total = len(chapters)
        if total == 0:
            logger.warning("No chapters_raw.json found — cannot build EPUB.")
            return

        timing_path = self.work_dir / "audio_timing.json"
        audio_timing = self._load_json(timing_path, default={})
        if not audio_timing:
            logger.warning("audio_timing.json missing or empty — EPUB will have no media overlays.")

        title = str(self.settings.book_title or "Untitled Book")
        author = str(self.settings.book_author or "Unknown Author")

        epub_work_dir = self.work_dir / "epub_build"
        epub_work_dir.mkdir(parents=True, exist_ok=True)

        builder = EPUBBuilder(
            title=title,
            author=author,
            output_dir=self.settings.output_dir,
            work_dir=str(epub_work_dir),
        )

        def _escape_html(text: str) -> str:
            return (
                text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
            )

        audio_root = self.work_dir / "audio"

        for idx, ch_entry in enumerate(chapters):
            if self._cancelled("epub_build"):
                return

            chapter_id = self._chapter_id_for_offset(idx)
            final_info_path = self._chapter_final_path(chapter_id)

            if not final_info_path.exists():
                logger.warning("Missing final chapter info for %s — skipping.", chapter_id)
                continue

            final_info = self._load_json(final_info_path, default={})
            segments = final_info.get("segments", [])
            if not segments:
                logger.warning("No segments in %s — skipping.", final_info_path)
                continue

            ch_title = (
                final_info.get("title")
                or ch_entry.get("title")
                or f"Chapter {idx + 1}"
            )

            body_parts: List[str] = []
            for seg in segments:
                text = _escape_html(str(seg.get("text", "") or ""))
                if not text:
                    continue
                pid = str(seg.get("paragraph_id", f"{chapter_id}_p0"))
                body_parts.append(f'<p id="{pid}">{text}</p>')

            xhtml_body = "\n".join(body_parts)
            chapter_filename = f"{chapter_id}.xhtml"

            xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <title>{_escape_html(ch_title)}</title>
  </head>
  <body>
    <h1>{_escape_html(ch_title)}</h1>
    {xhtml_body}
  </body>
</html>
"""

            builder.add_chapter(
                filename=chapter_filename,
                xhtml=xhtml,
                title=ch_title,
            )

            chapter_audio_dir = audio_root / chapter_id
            chapter_audio_path = chapter_audio_dir / f"{chapter_id}.wav"

            timings_raw = audio_timing.get(chapter_id, [])
            if chapter_audio_path.exists() and timings_raw:
                ts_segments: List[Dict] = []
                for t in timings_raw:
                    try:
                        ts_segments.append(
                            {
                                "paragraph_id": t.get("paragraph_id", ""),
                                "clip_begin": float(t.get("clip_begin", 0.0)),
                                "clip_end": float(t.get("clip_end", 0.0)),
                            }
                        )
                    except Exception:
                        logger.debug("Invalid timing entry for %s: %r", chapter_id, t, exc_info=True)

                if ts_segments:
                    builder.add_audio(
                        chapter_filename=chapter_filename,
                        audio_path=str(chapter_audio_path),
                        segments=ts_segments,
                    )
            else:
                logger.info(
                    "No audio or timing for %s — chapter will be text-only in EPUB.",
                    chapter_id,
                )

            percent = int((idx + 1) * 100 / max(total, 1))
            self._on_progress("epub_build", percent)

        epub_path = builder.build()
        logger.info("Phase 7 — EPUB build complete: %s", epub_path)
        self._on_progress("epub_build", 100)
