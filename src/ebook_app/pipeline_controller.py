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
from ebook_app.models.scraper import HttpWebScraper, WebScraper
from pathlib import Path
import json

from ebook_app.voice.voice_router import VoiceRouter


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
        "clean_chapters",
        "plan_clean_review",
        "llm_semantic_analysis",
        "normalize_llm_output",
        "smart_review_dialogue",
        "tts_generate",
        "epub_build",
    ]


    _OLLAMA_TAGS_PATH = "/api/tags"

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
        self.voice_router = VoiceRouter(
            character_voices=self.settings.character_voice_map,
             default_male_voice=self.settings.default_male_voice,
             default_female_voice=self.settings.default_female_voice,
             narrator_voice=self.settings.narrator_voice,
        )



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

    def _preflight_llm_check(self, parser) -> None:
        """Verify Ollama is reachable and the configured model is installed."""
        import requests
        from urllib.parse import urlparse, urlunparse

        try:
            parsed = urlparse(parser.ollama_url)
            if not parsed.scheme or not parsed.netloc:
                raise RuntimeError(
                    f"Invalid LLM URL {parser.ollama_url!r}. "
                    "Update the Ollama URL in Settings."
                )
            tags_url = urlunparse((parsed.scheme, parsed.netloc, self._OLLAMA_TAGS_PATH, "", "", ""))
            response = requests.get(tags_url, timeout=5)
            response.raise_for_status()
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Cannot connect to LLM at {parser.ollama_url!r}. "
                f"Ensure 'ollama serve' is running. Details: {exc}"
            ) from exc

        try:
            data = response.json()
            models_raw = data.get("models", []) if isinstance(data, dict) else []
            available = {
                str(m.get("name", "")).split(":")[0].strip()
                for m in models_raw
                if isinstance(m, dict)
            }
            model_base = str(parser.model or "").split(":")[0].strip()
            if model_base and model_base not in available:
                raise RuntimeError(
                    f"Model '{parser.model}' is not installed in Ollama. "
                    f"Pull it first: ollama pull {parser.model}"
                )
        except RuntimeError:
            raise
        except Exception:
            logger.debug(
                "Could not parse Ollama /api/tags response; skipping model presence check.",
                exc_info=True,
            )

    def _build_scraper(self):
        scraper_method = str(self.settings.get("scraper_method", "browser")).strip().lower()
        if scraper_method == "http":
            css_raw = (self.settings.get("scraper_css_selectors", "") or "").strip()
            css_selectors = [s.strip() for s in css_raw.split(",") if s.strip()] if css_raw else []
            excl_raw = (self.settings.get("scraper_exclude_selectors", "") or "").strip()
            exclude_selectors = [s.strip() for s in excl_raw.split(",") if s.strip()] if excl_raw else []
            scraper_kwargs = {
                "css_selectors": css_selectors,
                "exclude_selectors": exclude_selectors,
                "request_delay": int(self.settings.get("scraper_delay_ms", 500)) / 1000.0,
                "timeout": int(self.settings.get("scraper_browser_timeout_sec", 30)),
                "max_index_pages": int(self.settings.get("scraper_max_index_pages", 50)),
            }
            logger.debug("Creating HttpWebScraper with options: %s", scraper_kwargs)
            return HttpWebScraper(**scraper_kwargs)

        scraper_kwargs = {
            "wait_for_js": bool(self.settings.get("scraper_wait_for_js", True)),
            "remove_overlays": bool(self.settings.get("scraper_remove_overlays", True)),
            "browser_timeout": int(self.settings.get("scraper_browser_timeout_sec", 30)),
            "browser_headless": not bool(self.settings.get("scraper_use_browser_gui", False)),
            "manual_navigation": bool(self.settings.get("scraper_manual_navigation", False)),
            "manual_navigation_timeout_sec": int(
                self.settings.get("scraper_manual_navigation_timeout_sec", 120)
            ),
            "max_index_pages": int(self.settings.get("scraper_max_index_pages", 50)),
            "browser_channel": (self.settings.get("scraper_browser_channel", "") or "").strip() or None,
        }
        logger.debug("Creating WebScraper with options: %s", scraper_kwargs)
        try:
            return WebScraper(**scraper_kwargs)
        except TypeError:
            logger.debug(
                "WebScraper monkeypatch does not accept kwargs; retrying with defaults.",
                exc_info=True,
            )
            return WebScraper()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run_all(self) -> None:
        """Execute the full new pipeline."""
        self._running = True
        steps = [
            ("scrape_index", self.scrape_index),
            ("scrape_chapters", self.scrape_chapters),
            ("clean_chapters", self.clean_chapters),
            ("plan_clean_review", self.plan_clean_review),
            ("llm_semantic_analysis", self.llm_semantic_analysis),
            ("normalize_llm_output", self.normalize_llm_output),
            ("smart_review_dialogue", self.smart_review_dialogue),
            ("tts_generate", self.tts_generate),
            ("epub_build", self.epub_build),
        ]

        for key, method in steps:
            if not self._running:
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
    # Pipeline steps — Phase 1 & 2
    # ------------------------------------------------------------------

    def scrape_index(self) -> None:
        """Fetch the chapter index from the configured URL."""
        index_url = self.settings.get("index_url", "")
        if not index_url:
            logger.warning("No index_url configured in settings.")
            return

        logger.info(f"Scraping index from: {index_url}")
        scraper = self._build_scraper()
        max_index_pages = int(self.settings.get("scraper_max_index_pages", 50))
        try:
            self.raw_chapter_urls = scraper.scrape_index_page(index_url, max_pages=max_index_pages)
        except TypeError:
            logger.debug(
                "Scraper implementation does not accept max_pages kwarg; retrying without it.",
                exc_info=True,
            )
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
        logger.debug("Writing raw chapter URLs to %s", raw_urls_file)
        with open(raw_urls_file, "w", encoding="utf-8") as f:
            json.dump(self.raw_chapter_urls, f, indent=2, ensure_ascii=False)

        urls_file = self.work_dir / "chapter_urls.json"
        logger.debug("Writing filtered chapter URLs to %s", urls_file)
        with open(urls_file, "w", encoding="utf-8") as f:
            json.dump(self.chapter_urls, f, indent=2, ensure_ascii=False)

    def scrape_chapters(self) -> None:
        """Download all chapter pages listed in the scraped index."""
        if not self.chapter_urls:
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
        logger.debug("Selected chapter URL range: %s", selected_urls)
        scraper = self._build_scraper()
        self.chapters = scraper.scrape_chapters(selected_urls)

        chapters_file = self.work_dir / "chapters.json"
        logger.debug("Writing chapter scrape output to %s", chapters_file)
        with open(chapters_file, "w", encoding="utf-8") as f:
            json.dump(self.chapters, f, indent=2, ensure_ascii=False)

        logger.info(f"Scraped {len(self.chapters)} chapters successfully.")

    # ------------------------------------------------------------------
    # NEW Phase 3 — Deterministic cleaning
    # ------------------------------------------------------------------

    def clean_chapters(self) -> None:
        """Deterministically clean scraped chapters into per-chapter text files.

        This is a non-LLM, purely mechanical normalization step that prepares
        content for either user review or LLM semantic analysis.
        """
        if not self.chapters:
            chapters_file = self.work_dir / "chapters.json"
            if chapters_file.exists():
                with open(chapters_file, encoding="utf-8") as f:
                    self.chapters = json.load(f)
            else:
                logger.warning("No chapters available. Run scrape_chapters first.")
                return

        total = len(self.chapters)
        if total == 0:
            logger.warning("No chapters to clean.")
            return

        logger.info("Cleaning %d chapters (deterministic, no LLM)…", total)
        for idx, chapter in enumerate(self.chapters):
            chapter_id = f"ch{idx:03d}"
            raw_content = str(chapter.get("content", "") or "")

            # Simple deterministic cleaning; can be refined later.
            text = raw_content.replace("\r\n", "\n").replace("\r", "\n")
            lines = [ln.strip() for ln in text.split("\n")]
            lines = [ln for ln in lines if ln]  # drop empty lines
            cleaned = "\n\n".join(lines)

            out_path = self.work_dir / f"{chapter_id}_cleaned.txt"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(cleaned)

            self._on_progress("clean_chapters", int((idx + 1) * 100 / max(total, 1)))

        logger.info("Deterministic cleaning complete for %d chapters.", total)

    # ------------------------------------------------------------------
    # NEW Phase 4 — Cleaned-text review planner
    # ------------------------------------------------------------------

    def plan_clean_review(self) -> None:
        """Plan which chapters require manual cleaned-text review.

        Uses:
          - clean_review_mode: 'skip', 'semi', 'full'
          - clean_review_sample_chapters: N (for 'semi')
        Writes:
          - clean_review_plan.json in work_dir
        """
        mode = str(self.settings.get("clean_review_mode", "semi")).strip().lower()
        sample_n = int(self.settings.get("clean_review_sample_chapters", 3))

        chapters_file = self.work_dir / "chapters.json"
        if chapters_file.exists():
            with open(chapters_file, encoding="utf-8") as f:
                chapters = json.load(f)
        else:
            chapters = self.chapters or []
        total = len(chapters)

        if total == 0:
            logger.warning("No chapters available to plan cleaned-text review.")
            return

        if mode not in {"skip", "semi", "full"}:
            logger.warning("Unknown clean_review_mode=%r; defaulting to 'semi'.", mode)
            mode = "semi"

        if mode == "skip":
            needs_review: list[int] = []
        elif mode == "full":
            needs_review = list(range(total))
        else:  # 'semi'
            needs_review = list(range(min(sample_n, total)))

        plan = {
            "mode": mode,
            "sample": sample_n,
            "total_chapters": total,
            "needs_review": needs_review,
        }
        plan_path = self.work_dir / "clean_review_plan.json"
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)

        logger.info(
            "Cleaned-text review plan written to %s (mode=%s, needs_review=%s)",
            plan_path,
            mode,
            needs_review,
        )

          
    # ------------------------------------------------------------------
    # PHASE 5 — LLM Semantic Analysis
    # ------------------------------------------------------------------

    def llm_semantic_analysis(self) -> None:
        """
        Phase 5:
        - Load cleaned_final text (or cleaned if skip mode)
        - Run DialogueParser.parse() for each chapter
        - Save raw LLM output to chXXX_llm_raw.json
        - Save per-chapter chapter_info.json
        """
        logger.info("Running Phase 5 — LLM Semantic Analysis…")

        # Load cleaned review plan
        plan_path = self.work_dir / "clean_review_plan.json"
        if plan_path.exists():
            with open(plan_path, "r", encoding="utf-8") as f:
                review_plan = json.load(f)
        else:
            review_plan = {"needs_review": []}

        # Load chapters.json (for titles)
        chapters_file = self.work_dir / "chapters.json"
        if not chapters_file.exists():
            logger.error("Missing chapters.json — cannot run semantic analysis.")
            return
        with open(chapters_file, "r", encoding="utf-8") as f:
            chapters = json.load(f)

        total = len(chapters)
        if total == 0:
            logger.warning("No chapters available for semantic analysis.")
            return

        # Prepare LLM parser
        llm_url = self.settings.get("dialogue_llm_url", "") or self.settings.get("ollama_url", "")
        llm_model = self.settings.get("dialogue_llm_model", "") or self.settings.get("ollama_model", "")
        llm_log_path = self.work_dir / "llm_communication.jsonl"

        parser = DialogueParser(
            ollama_url=llm_url,
            model=llm_model,
            timeout_s=int(self.settings.get("dialogue_llm_timeout", 120)),
            retries=int(self.settings.get("dialogue_llm_retries", 1)),
            llm_mode=str(self.settings.get("dialogue_llm_mode", "full")),
            llm_strict_quotes=bool(self.settings.get("dialogue_llm_strict_quotes", False)),
            llm_log_path=str(llm_log_path),
        )

        # Optional preflight check
        if bool(self.settings.get("llm_preflight_check", True)):
            self._preflight_llm_check(parser)

        aggregated_info = {}

        for idx, chapter in enumerate(chapters):
            chapter_id = f"ch{idx:03d}"
            title = chapter.get("title", f"Chapter {idx + 1}")

            # Determine which cleaned file to use
            cleaned_final = self.work_dir / f"{chapter_id}_cleaned_final.txt"
            cleaned_basic = self.work_dir / f"{chapter_id}_cleaned.txt"

            if cleaned_final.exists():
                with open(cleaned_final, "r", encoding="utf-8") as f:
                    text = f.read()
            elif cleaned_basic.exists():
                with open(cleaned_basic, "r", encoding="utf-8") as f:
                    text = f.read()
            else:
                logger.warning("Missing cleaned text for %s — skipping.", chapter_id)
                continue

            # Run LLM semantic parsing
            result = parser.parse(text=text, chapter_id=chapter_id)
            self.dialogue_segments[idx] = result.segments

            # Build chapter_info structure
            chapter_info = {
                "chapter_index": idx,
                "chapter_id": chapter_id,
                "title": title,
                "segments": [
                    {
                        "text": s.text,
                        "type": s.type,
                        "speaker": s.speaker,
                        "gender": s.gender,
                        "speaker_confidence": s.speaker_confidence,
                        "gender_confidence": s.gender_confidence,
                        "character_confidence": s.character_confidence,
                        "paragraph_id": s.paragraph_id,
                    }
                    for s in result.segments
                ],
                "detected_characters": [
                    {
                        "name": c.name,
                        "gender": c.gender,
                        "confidence": c.confidence,
                    }
                    for c in result.detected_characters
                ],
            }

            # Save raw LLM output
            raw_path = self.work_dir / f"{chapter_id}_llm_raw.json"
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump(chapter_info, f, indent=2, ensure_ascii=False)

            # Save per-chapter chapter_info.json
            chapter_dir = self.work_dir / chapter_id
            chapter_dir.mkdir(parents=True, exist_ok=True)
            with open(chapter_dir / "chapter_info.json", "w", encoding="utf-8") as f:
                json.dump(chapter_info, f, indent=2, ensure_ascii=False)

            aggregated_info[str(idx)] = chapter_info

            self._on_progress("llm_semantic_analysis", int((idx + 1) * 100 / total))

        # Save aggregated chapter_info.json
        with open(self.work_dir / "chapter_info.json", "w", encoding="utf-8") as f:
            json.dump(aggregated_info, f, indent=2, ensure_ascii=False)

        logger.info("Phase 5 — LLM Semantic Analysis complete.")

           
    # ------------------------------------------------------------------
    # PHASE 6 — Normalize + Smart Review + Voice Assignment
    # ------------------------------------------------------------------

    def normalize_llm_output(self) -> None:
        """
        Phase 6A:
        Convert chXXX_llm_raw.json → chXXX_llm_normalized.json
        Ensures a strict schema for downstream processing.
        """
        logger.info("Running Phase 6A — Normalizing LLM output…")

        chapters_file = self.work_dir / "chapters.json"
        if not chapters_file.exists():
            logger.error("Missing chapters.json — cannot normalize.")
            return
        with open(chapters_file, "r", encoding="utf-8") as f:
            chapters = json.load(f)

        total = len(chapters)
        for idx in range(total):
            chapter_id = f"ch{idx:03d}"
            raw_path = self.work_dir / f"{chapter_id}_llm_raw.json"
            if not raw_path.exists():
                logger.warning("Missing raw LLM output for %s — skipping.", chapter_id)
                continue

            with open(raw_path, "r", encoding="utf-8") as f:
                raw = json.load(f)

            # Normalize segments
            normalized_segments = []
            for seg in raw.get("segments", []):
                normalized_segments.append({
                    "text": seg.get("text", ""),
                    "type": seg.get("type", "narration"),
                    "speaker": seg.get("speaker", "narrator"),
                    "gender": seg.get("gender", "unknown"),
                    "speaker_confidence": float(seg.get("speaker_confidence", 1.0)),
                    "gender_confidence": float(seg.get("gender_confidence", 0.0)),
                    "character_confidence": float(seg.get("character_confidence", 1.0)),
                    "paragraph_id": seg.get("paragraph_id", f"{chapter_id}_p0"),
                })

            # Normalize characters
            normalized_chars = []
            for c in raw.get("detected_characters", []):
                normalized_chars.append({
                    "name": c.get("name", ""),
                    "gender": c.get("gender", "unknown"),
                    "confidence": float(c.get("confidence", 0.0)),
                })

            normalized = {
                "chapter_id": chapter_id,
                "segments": normalized_segments,
                "characters": normalized_chars,
            }

            out_path = self.work_dir / f"{chapter_id}_llm_normalized.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(normalized, f, indent=2, ensure_ascii=False)

            self._on_progress("normalize_llm_output", int((idx + 1) * 100 / total))

        logger.info("Phase 6A — Normalization complete.")

    # ------------------------------------------------------------------

    def smart_review_dialogue(self) -> None:
        """
        Phase 6B:
        Smart auto-review + voice assignment.

        - Auto-approve chapters unless:
            * new characters appear
            * low speaker_confidence
            * low character_confidence
        - Assign voices (default + character_db)
        - Write final JSON files
        - Update character_db + pending additions
        """
        logger.info("Running Phase 6B — Smart Review + Voice Assignment…")

        # Load thresholds
        speaker_thresh = float(self.settings.get("speaker_conf_threshold", 0.8))
        char_thresh = float(self.settings.get("character_conf_threshold", 0.8))

        # Load existing character DB
        character_db = self.settings.get("character_db", []) or []
        known_names = {self._normalize_name(c["name"]) for c in character_db if c.get("name")}

        pending = self.settings.get("pending_character_additions", []) or []
        pending_names = {self._normalize_name(c["name"]) for c in pending if c.get("name")}

        # Default voices
        narrator_voice = self.settings.get("narrator_voice", "af_heart")
        default_male = self.settings.get("default_male_voice", "am_adam")
        default_female = self.settings.get("default_female_voice", "af_heart")

        # Load chapters.json
        chapters_file = self.work_dir / "chapters.json"
        with open(chapters_file, "r", encoding="utf-8") as f:
            chapters = json.load(f)
        total = len(chapters)

        # Track which chapters require manual review
        needs_review = []

        for idx in range(total):
            chapter_id = f"ch{idx:03d}"
            norm_path = self.work_dir / f"{chapter_id}_llm_normalized.json"
            if not norm_path.exists():
                logger.warning("Missing normalized LLM output for %s — skipping.", chapter_id)
                continue

            with open(norm_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            segments = data.get("segments", [])
            detected_chars = data.get("characters", [])

            # ------------------------------------------------------
            # SMART REVIEW TRIGGERS
            # ------------------------------------------------------
            review_flag = False

            # 1. New characters
            for c in detected_chars:
                norm = self._normalize_name(c["name"])
                if norm and norm not in known_names and norm not in pending_names:
                    review_flag = True

            # 2. Low confidence segments
            for seg in segments:
                if seg["speaker_confidence"] < speaker_thresh:
                    review_flag = True
                if seg["character_confidence"] < char_thresh:
                    review_flag = True

            if review_flag:
                needs_review.append(idx)
            else:
                # AUTO-APPROVE → write final files immediately
                self._write_final_chapter_files(
                    chapter_id=chapter_id,
                    segments=segments,
                    detected_chars=detected_chars,
                    narrator_voice=narrator_voice,
                    default_male=default_male,
                    default_female=default_female,
                    character_db=character_db,
                )

            self._on_progress("smart_review_dialogue", int((idx + 1) * 100 / total))

        # Save review plan
        review_plan = {
            "needs_review": needs_review,
            "total_chapters": total,
        }
        with open(self.work_dir / "semantic_review_plan.json", "w", encoding="utf-8") as f:
            json.dump(review_plan, f, indent=2, ensure_ascii=False)

        # Update settings
        self.settings.set("pending_character_additions", pending)
        self.settings.set("character_db", character_db)

        logger.info("Phase 6B — Smart Review complete.")
        logger.info("Chapters requiring manual review: %s", needs_review)

    # ------------------------------------------------------------------

    def _write_final_chapter_files(
        self,
        chapter_id: str,
        segments: list,
        detected_chars: list,
        narrator_voice: str,
        default_male: str,
        default_female: str,
        character_db: list,
    ) -> None:
        """
        Helper for Phase 6:
        Writes:
          - chXXX_segments_final.json
          - chXXX_characters_final.json
        Applies voice assignment.
        """
        # Build voice map from character_db
        voice_map = {
            self._normalize_name(c["name"]): c.get("voice", narrator_voice)
            for c in character_db
        }

        # Assign voices
        final_chars = []
        for c in detected_chars:
            name = c["name"]
            norm = self._normalize_name(name)
            gender = c.get("gender", "unknown").lower()

            if norm in voice_map:
                voice = voice_map[norm]
            else:
                # Default assignment
                if gender == "male":
                    voice = default_male
                elif gender == "female":
                    voice = default_female
                else:
                    voice = narrator_voice

                # Add to character_db
                character_db.append({
                    "name": name,
                    "gender": gender,
                    "voice": voice,
                    "description": "",
                })
                voice_map[norm] = voice

            final_chars.append({
                "name": name,
                "gender": gender,
                "voice": voice,
            })

        # Write segments_final
        seg_path = self.work_dir / f"{chapter_id}_segments_final.json"
        with open(seg_path, "w", encoding="utf-8") as f:
            json.dump(segments, f, indent=2, ensure_ascii=False)

        # Write characters_final
        char_path = self.work_dir / f"{chapter_id}_characters_final.json"
        with open(char_path, "w", encoding="utf-8") as f:
            json.dump(final_chars, f, indent=2, ensure_ascii=False)
       
    # ------------------------------------------------------------------
    # PHASE 7 — TTS Generation (new pipeline)
    # ------------------------------------------------------------------

    def tts_generate(self) -> None:
        """
        Phase 7:
        - Load final segments + character voices
        - Build voice map from character_db
        - Generate audio per chapter or whole book
        - Write audio to work_dir/audio/
        """
        logger.info("Running Phase 7 — TTS Generation…")

        audio_dir = self.work_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        # Load character DB
        character_db = self.settings.get("character_db", []) or []
        voice_map = {
            self._normalize_name(c["name"]): c.get("voice", "")
            for c in character_db
        }

        narrator_voice = self.settings.get("narrator_voice", "af_heart")
        default_male = self.settings.get("default_male_voice", "am_adam")
        default_female = self.settings.get("default_female_voice", "af_heart")

        # Build TTS backend
        engine = self._make_tts_backend(output_dir=str(audio_dir))

        # Load chapters.json
        chapters_file = self.work_dir / "chapters.json"
        with open(chapters_file, "r", encoding="utf-8") as f:
            chapters = json.load(f)
        total = len(chapters)

        audio_mode = self.settings.get("audio_output_mode", "per_chapter")

        # --------------------------------------------------------------
        # SINGLE FILE MODE
        # --------------------------------------------------------------
        if audio_mode == "single_file":
            logger.info("Generating single-file audiobook…")

            full_text = []
            for idx in range(total):
                chapter_id = f"ch{idx:03d}"
                seg_path = self.work_dir / f"{chapter_id}_segments_final.json"
                if not seg_path.exists():
                    continue
                with open(seg_path, "r", encoding="utf-8") as f:
                    segs = json.load(f)
                for s in segs:
                    full_text.append(s["text"])

            combined = "\n\n".join(full_text).strip()
            if not combined:
                logger.warning("No text available for TTS.")
                return

            out_path = engine.generate_audio(
                text=combined,
                output_filename="book_audio.wav",
                voice=narrator_voice,
                speed=self.settings.tts_speed,
            )
            self.audio_files = {0: out_path}

            logger.info("Phase 7 — Single-file TTS complete.")
            return

        # --------------------------------------------------------------
        # PER-CHAPTER MODE
        # --------------------------------------------------------------
        logger.info("Generating per-chapter audio…")

        for idx in range(total):
            chapter_id = f"ch{idx:03d}"
            seg_path = self.work_dir / f"{chapter_id}_segments_final.json"
            char_path = self.work_dir / f"{chapter_id}_characters_final.json"

            if not seg_path.exists():
                logger.warning("Missing final segments for %s — skipping.", chapter_id)
                continue

            with open(seg_path, "r", encoding="utf-8") as f:
                segments = json.load(f)

            # Build text for narration-only TTS
            text_parts = [s["text"] for s in segments if s["text"].strip()]
            full_text = "\n\n".join(text_parts).strip()
            if not full_text:
                logger.warning("Chapter %s has no text for TTS.", chapter_id)
                continue

            output_filename = f"{chapter_id}.wav"
            out_path = engine.generate_audio(
                text=full_text,
                output_filename=output_filename,
                voice=narrator_voice,
                speed=self.settings.tts_speed,
            )
            self.audio_files[idx] = out_path

            self._on_progress("tts_generate", int((idx + 1) * 100 / total))

        logger.info("Phase 7 — Per-chapter TTS complete.")
        
    # ------------------------------------------------------------------
    # PHASE 8 — EPUB Build (new pipeline)
    # ------------------------------------------------------------------

    def epub_build(self) -> None:
        """
        Phase 8:
        - Build XHTML from final segments
        - Build SMIL overlays from alignment data (if available)
        - Use EPUBBuilder to produce final .epub
        """
        logger.info("Running Phase 8 — EPUB Build…")

        # Load chapters
        chapters_file = self.work_dir / "chapters.json"
        if not chapters_file.exists():
            logger.error("Missing chapters.json — cannot build EPUB.")
            return
        with open(chapters_file, "r", encoding="utf-8") as f:
            chapters = json.load(f)

        # Metadata (project manager can override later)
        title = "Book"
        author = "Unknown"

        builder = EPUBBuilder(
            title=title,
            author=author,
            output_dir=str(self.settings.output_dir),
        )

        total = len(chapters)

        for idx, chapter in enumerate(chapters):
            chapter_id = f"ch{idx:03d}"
            chapter_title = chapter.get("title", f"Chapter {idx + 1}")

            seg_path = self.work_dir / f"{chapter_id}_segments_final.json"
            if not seg_path.exists():
                logger.warning("Missing final segments for %s — skipping.", chapter_id)
                continue

            with open(seg_path, "r", encoding="utf-8") as f:
                segments = json.load(f)

            # Build XHTML
            xhtml_lines = [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<!DOCTYPE html>',
                '<html xmlns="http://www.w3.org/1999/xhtml">',
                "<head>",
                f"<title>{chapter_title}</title>",
                '<link rel="stylesheet" type="text/css" href="stylesheet.css"/>',
                "</head>",
                "<body>",
                f"<h1>{chapter_title}</h1>",
            ]

            for s in segments:
                pid = s["paragraph_id"]
                text = s["text"]
                xhtml_lines.append(f'<p id="{pid}">{text}</p>')

            xhtml_lines.append("</body></html>")
            xhtml = "\n".join(xhtml_lines)

            filename = f"{chapter_id}.xhtml"
            builder.add_chapter(filename=filename, xhtml=xhtml, title=chapter_title)

            # Attach audio if available
            audio_path = self.audio_files.get(idx)
            if audio_path:
                # Build simple SMIL segments (no forced alignment yet)
                smil_segments = []
                for s in segments:
                    smil_segments.append(
                        TextSegment(
                            paragraph_id=s["paragraph_id"],
                            clip_begin=0.0,
                            clip_end=0.0,
                        )
                    )
                builder.add_audio(
                    chapter_filename=filename,
                    audio_path=str(audio_path),
                    segments=smil_segments,
                )

            self._on_progress("epub_build", int((idx + 1) * 100 / total))

        out_path = builder.build()
        logger.info("Phase 8 — EPUB Build complete: %s", out_path)
   
   
    def tts_generate_segment(
        self,
        chapter_index: int,
        segment_index: int,
        *,
        preview_mode: bool = True,
    ) -> Path:
        """Generate TTS audio for a single semantic segment.

        Returns:
            Path to the generated WAV file.
        """
        # 1) Locate chapter_info.json
        work_dir: Path = self.project.get_work_dir()  # or self.work_dir / self.project.work_dir
        chapter_id = f"ch{chapter_index:03d}"
        info_file = work_dir / chapter_id / "chapter_info.json"

        if not info_file.exists():
            raise FileNotFoundError(f"chapter_info.json not found for {chapter_id}")

        data = json.loads(info_file.read_text(encoding="utf-8"))
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

        seg_type = seg.get("type", "narration")
        speaker = seg.get("speaker", "narrator")

        # 2) Decide voice based on speaker/segment type
        #    (adapt this to your real voice-mapping logic)
        voice_name = self.voice_router.get_voice_for_speaker(speaker, seg_type) \
            if hasattr(self, "voice_router") else self.settings.default_voice

        # 3) Build output path
        preview_dir = work_dir / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        out_path = preview_dir / f"{chapter_id}_seg{segment_index:03d}_preview.wav"

        # 4) Call existing TTS backend client
        #    Replace `self.tts_client.synthesize` with your actual low-level call.
        self.log.info(
            f"TTS segment preview: chapter={chapter_id}, segment={segment_index}, "
            f"type={seg_type}, speaker={speaker}, voice={voice_name}"
        )

        self.tts_client.synthesize(
            text=text,
            voice=voice_name,
            output_path=out_path,
            speed=self.settings.tts_speed,
            emotion=seg.get("emotion"),  # if you support this
            preview_mode=preview_mode,
        )

        return out_path