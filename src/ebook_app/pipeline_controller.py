# src/ebook_app/pipeline_controller.py
"""Pipeline orchestration controller — runs the end-to-end processing pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from ebook_app.core.epub.epub_builder import EPUBBuilder
from ebook_app.core.tts.voice_router import VoiceRouter
from ebook_app.models.book_library import FillerChapterFilter
from ebook_app.models.dialogue_parser import DialogueParser, Segment
from ebook_app.models.scraper import HttpWebScraper, WebScraper
from ebook_app.pipeline_contracts import TextSegment

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ebook_app.core.settings_manager import SettingsManager

# Progress callback type: (step_key, value 0-100) -> None
ProgressCallback = Callable[[str, int], None]


class PipelineController:
    """Orchestrates the full Web-Novel → EPUB3 Audiobook pipeline."""

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

        # Work directory
        if work_dir:
            self.work_dir = Path(work_dir)
        else:
            self.work_dir = Path(self.settings.output_dir) / "pipeline_work"
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Pipeline state
        self.chapter_urls: list[str] = []
        self.raw_chapter_urls: list[str] = []
        self.chapters: list[dict] = []
        self.dialogue_segments: dict[int, list[Segment]] = {}
        self.audio_files: dict[int, Path] = {}

        self.selected_start_chapter: int = 1
        self.selected_end_chapter: int = 0

        # Future-ready semantic + review state
        self.clean_review_plan: dict = {}
        self.semantic_review_plan: dict = {}
        self.character_db: list[dict] = []

        # Voice routing
        self.voice_router = VoiceRouter(
            character_voices=self.settings.get("character_voice_map", {}) or {},
            default_male_voice=str(self.settings.get("default_male_voice", "am_adam")),
            default_female_voice=str(self.settings.get("default_female_voice", "af_heart")),
            narrator_voice=str(self.settings.get("narrator_voice", "af_heart")),
        )

    # ------------------------------------------------------------------
    # Helper utilities
    # ------------------------------------------------------------------

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

    def _load_json(self, path: Path, default=None):
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.error("Failed to load JSON from %s", path, exc_info=True)
            return default

    def _save_json(self, path: Path, data) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logger.error("Failed to save JSON to %s", path, exc_info=True)

    @staticmethod
    def _chapter_id(idx: int) -> str:
        return f"ch{idx:03d}"

    # ------------------------------------------------------------------
    # TTS backend factory
    # ------------------------------------------------------------------

    def _make_tts_backend(self, output_dir: str | None = None):
        """Return the contract-compliant TTS backend."""
        effective_output_dir = output_dir or str(self.work_dir / "audio")
        from ebook_app.core.tts.tts_engine import TTSEngine
        return TTSEngine(
            output_dir=effective_output_dir,
            server_url=str(self.settings.get("tts_backend_url", "http://127.0.0.1:5005")),
        )

    # ------------------------------------------------------------------
    # LLM preflight
    # ------------------------------------------------------------------

    def _preflight_llm_check(self, parser) -> None:
        """Verify Ollama is reachable and the configured model is installed."""
        import requests
        from urllib.parse import urlparse, urlunparse

        try:
            parsed = urlparse(parser.ollama_url)
            if not parsed.scheme or not parsed.netloc:
                raise RuntimeError(
                    f"Invalid LLM URL {parser.ollama_url!r}. Update the Ollama URL in Settings."
                )

            tags_url = urlunparse((parsed.scheme, parsed.netloc, self._OLLAMA_TAGS_PATH, "", "", ""))
            response = requests.get(tags_url, timeout=5)
            response.raise_for_status()
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
            logger.debug("Could not parse Ollama /api/tags response; skipping model presence check.", exc_info=True)

    # ------------------------------------------------------------------
    # Scraper builder
    # ------------------------------------------------------------------

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
        steps = [(name, getattr(self, name)) for name in self.STEPS]

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

        self._save_json(
            self.work_dir / "selected_range.json",
            {"start": start, "end": end},
        )

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

        logger.info(f"[Phase 1] Scraping index from: {index_url}")
        scraper = self._build_scraper()
        max_index_pages = int(self.settings.get("scraper_max_index_pages", 50))

        try:
            self.raw_chapter_urls = scraper.scrape_index_page(
                index_url, max_pages=max_index_pages
            )
        except TypeError:
            logger.debug(
                "Scraper implementation does not accept max_pages kwarg; retrying without it.",
                exc_info=True,
            )
            self.raw_chapter_urls = scraper.scrape_index_page(index_url)

        url_filter = FillerChapterFilter()
        self.chapter_urls, filtered_urls = url_filter.filter_urls(self.raw_chapter_urls)

        logger.info(
            "Index scrape complete: %d total, %d valid, %d filtered.",
            len(self.raw_chapter_urls),
            len(self.chapter_urls),
            len(filtered_urls),
        )

        self._save_json(self.work_dir / "raw_chapter_urls.json", self.raw_chapter_urls)
        self._save_json(self.work_dir / "chapter_urls.json", self.chapter_urls)

        self._on_progress("scrape_index", 100)

    def scrape_chapters(self) -> None:
        """Download all chapter pages listed in the scraped index."""
        logger.info("[Phase 2] Scraping chapters…")

        # Load chapter URLs if needed
        if not self.chapter_urls:
            self.chapter_urls = self._load_json(
                self.work_dir / "chapter_urls.json", default=[]
            )

        if not self.chapter_urls:
            logger.warning("No chapter URLs available. Run scrape_index first.")
            return

        # Determine range
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

        scraper = self._build_scraper()
        self.chapters = scraper.scrape_chapters(selected_urls)

        self._save_json(self.work_dir / "chapters.json", self.chapters)

        logger.info("Scraped %d chapters successfully.", len(self.chapters))
        self._on_progress("scrape_chapters", 100)

    # ------------------------------------------------------------------
    # NEW Phase 3 — Deterministic cleaning
    # ------------------------------------------------------------------

    def clean_chapters(self) -> None:
        """Deterministically clean scraped chapters into per-chapter text files."""
        logger.info("[Phase 3] Cleaning chapters (deterministic)…")

        if not self.chapters:
            self.chapters = self._load_json(
                self.work_dir / "chapters.json", default=[]
            )

        total = len(self.chapters)
        if total == 0:
            logger.warning("No chapters to clean.")
            return

        for idx, chapter in enumerate(self.chapters):
            chapter_id = self._chapter_id(idx)
            raw_content = str(chapter.get("content", "") or "")

            # Simple deterministic cleaning
            text = raw_content.replace("\r\n", "\n").replace("\r", "\n")
            lines = [ln.strip() for ln in text.split("\n")]
            lines = [ln for ln in lines if ln]  # drop empty lines
            cleaned = "\n\n".join(lines)

            out_path = self.work_dir / f"{chapter_id}_cleaned.txt"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(cleaned, encoding="utf-8")

            # Improved progress reporting
            percent = int((idx + 1) * 100 / max(total, 1))
            logger.debug("Cleaned %s (%d/%d)", chapter_id, idx + 1, total)
            self._on_progress("clean_chapters", percent)

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
        logger.info("[Phase 4] Planning cleaned-text review…")

        mode = str(self.settings.get("clean_review_mode", "semi")).strip().lower()
        sample_n = int(self.settings.get("clean_review_sample_chapters", 3))

        chapters = self._load_json(self.work_dir / "chapters.json", default=[])
        total = len(chapters)

        if total == 0:
            logger.warning("No chapters available to plan cleaned-text review.")
            return

        if mode not in {"skip", "semi", "full"}:
            logger.warning("Unknown clean_review_mode=%r; defaulting to 'semi'.", mode)
            mode = "semi"

        if mode == "skip":
            needs_review = []
        elif mode == "full":
            needs_review = list(range(total))
        else:  # semi
            needs_review = list(range(min(sample_n, total)))

        plan = {
            "mode": mode,
            "sample": sample_n,
            "total_chapters": total,
            "needs_review": needs_review,
        }

        self.clean_review_plan = plan
        self._save_json(self.work_dir / "clean_review_plan.json", plan)

        logger.info(
            "Cleaned-text review plan created (mode=%s, needs_review=%s)",
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
        - Save per-chapter chXXX_chapter_info.json
        - Save aggregated chapter_info_all.json
        """
        logger.info("[Phase 5] Running LLM Semantic Analysis…")

        # Load cleaned review plan
        review_plan = self._load_json(
            self.work_dir / "clean_review_plan.json",
            default={"needs_review": []},
        )

        # Load chapters.json (for titles)
        chapters = self._load_json(self.work_dir / "chapters.json", default=[])
        total = len(chapters)

        if total == 0:
            logger.error("Missing chapters.json — cannot run semantic analysis.")
            return

        # Prepare LLM parser
        llm_url = self.settings.get("dialogue_llm_url", "")
        llm_model = self.settings.get("dialogue_llm_model", "")
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
            chapter_id = self._chapter_id(idx)
            title = chapter.get("title", f"Chapter {idx + 1}")

            # Determine which cleaned file to use
            cleaned_final = self.work_dir / f"{chapter_id}_cleaned_final.txt"
            cleaned_basic = self.work_dir / f"{chapter_id}_cleaned.txt"

            if cleaned_final.exists():
                text = cleaned_final.read_text(encoding="utf-8")
            elif cleaned_basic.exists():
                text = cleaned_basic.read_text(encoding="utf-8")
            else:
                logger.warning("Missing cleaned text for %s — skipping.", chapter_id)
                continue

            # Run LLM semantic parsing
            logger.debug("Parsing chapter %s (%d/%d)…", chapter_id, idx + 1, total)
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
            self._save_json(raw_path, chapter_info)

            # Save per-chapter chapter_info
            chapter_dir = self.work_dir / chapter_id
            chapter_dir.mkdir(parents=True, exist_ok=True)
            self._save_json(chapter_dir / "chXXX_chapter_info.json".replace("XXX", chapter_id[2:]), chapter_info)

            aggregated_info[str(idx)] = chapter_info

            percent = int((idx + 1) * 100 / total)
            self._on_progress("llm_semantic_analysis", percent)

        # Save aggregated chapter_info_all.json
        self._save_json(self.work_dir / "chapter_info_all.json", aggregated_info)

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
        logger.info("[Phase 6A] Normalizing LLM output…")

        chapters = self._load_json(self.work_dir / "chapters.json", default=[])
        total = len(chapters)

        if total == 0:
            logger.error("Missing chapters.json — cannot normalize.")
            return

        for idx in range(total):
            chapter_id = self._chapter_id(idx)
            raw_path = self.work_dir / f"{chapter_id}_llm_raw.json"

            if not raw_path.exists():
                logger.warning("Missing raw LLM output for %s — skipping.", chapter_id)
                continue

            raw = self._load_json(raw_path, default={})

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
            self._save_json(out_path, normalized)

            percent = int((idx + 1) * 100 / total)
            self._on_progress("normalize_llm_output", percent)

        logger.info("Phase 6A — Normalization complete.")

    # ------------------------------------------------------------------
    # PHASE 6 — Normalize + Smart Review + Voice Assignment
    # ------------------------------------------------------------------

    def smart_review_dialogue(self) -> None:
        """
        Phase 6B:
        Smart auto-review + voice assignment.

        - Detect new characters
        - Detect low-confidence segments
        - Detect gender inconsistencies
        - Detect alias collisions
        - Detect unknown speakers
        - Assign voices (VoiceRouter for known, fallback for unknown)
        - Write final JSON files
        - Update character_database.json
        - Write semantic_review_plan.json
        """
        logger.info("[Phase 6B] Smart Review + Voice Assignment…")

        # Load thresholds
        speaker_thresh = float(self.settings.get("speaker_conf_threshold", 0.8))
        char_thresh = float(self.settings.get("character_conf_threshold", 0.8))

        # Load character DB from file (new canonical location)
        db_path = self.work_dir / "character_database.json"
        character_db = self._load_json(db_path, default=[])
        self.character_db = character_db

        known_names = {self._normalize_name(c["name"]) for c in character_db if c.get("name")}

        # Pending additions (still stored in settings for UI)
        pending = self.settings.get("pending_character_additions", []) or []
        pending_names = {self._normalize_name(c["name"]) for c in pending if c.get("name")}

        # Default voices
        narrator_voice = self.settings.get("narrator_voice", "af_heart")
        default_male = self.settings.get("default_male_voice", "am_adam")
        default_female = self.settings.get("default_female_voice", "af_heart")

        # Load chapters.json
        chapters = self._load_json(self.work_dir / "chapters.json", default=[])
        total = len(chapters)

        needs_review = []

        for idx in range(total):
            chapter_id = self._chapter_id(idx)
            norm_path = self.work_dir / f"{chapter_id}_llm_normalized.json"

            if not norm_path.exists():
                logger.warning("Missing normalized LLM output for %s — skipping.", chapter_id)
                continue

            data = self._load_json(norm_path, default={})
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

            # 3. Gender inconsistencies
            gender_map = {}
            for c in detected_chars:
                norm = self._normalize_name(c["name"])
                g = c.get("gender", "unknown")
                if norm in gender_map and gender_map[norm] != g:
                    review_flag = True
                gender_map[norm] = g

            # 4. Alias collisions (same normalized name, different raw names)
            alias_map = {}
            for c in detected_chars:
                norm = self._normalize_name(c["name"])
                alias_map.setdefault(norm, set()).add(c["name"])
            for norm, raw_names in alias_map.items():
                if len(raw_names) > 1:
                    review_flag = True

            # 5. Unknown speakers
            for seg in segments:
                sp = seg.get("speaker", "").strip()
                if sp and self._normalize_name(sp) not in known_names:
                    # Unknown speaker → review unless narrator
                    if sp.lower() not in {"narrator", "unknown"}:
                        review_flag = True

            # ------------------------------------------------------
            # AUTO-APPROVE OR FLAG FOR REVIEW
            # ------------------------------------------------------
            if review_flag:
                needs_review.append(idx)
            else:
                self._write_final_chapter_files(
                    chapter_id=chapter_id,
                    segments=segments,
                    detected_chars=detected_chars,
                    narrator_voice=narrator_voice,
                    default_male=default_male,
                    default_female=default_female,
                    character_db=character_db,
                )

            percent = int((idx + 1) * 100 / total)
            self._on_progress("smart_review_dialogue", percent)

        # Save review plan
        review_plan = {
            "needs_review": needs_review,
            "total_chapters": total,
        }
        self.semantic_review_plan = review_plan
        self._save_json(self.work_dir / "semantic_review_plan.json", review_plan)

        # Update character DB file
        self._save_json(db_path, character_db)

        # Update settings (UI still reads these)
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
          - chXXX_chapter_info_final.json
        Applies hybrid voice assignment:
          - VoiceRouter for known characters
          - Fallback logic for unknown characters
        """
        # Build voice map from character_db
        voice_map = {
            self._normalize_name(c["name"]): c.get("voice", narrator_voice)
            for c in character_db
        }

        final_chars = []

        for c in detected_chars:
            name = c["name"]
            norm = self._normalize_name(name)
            gender = c.get("gender", "unknown").lower()

            # Hybrid voice assignment
            if norm in voice_map:
                voice = voice_map[norm]
            else:
                # Unknown character → fallback
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
        self._save_json(seg_path, segments)

        # Write characters_final
        char_path = self.work_dir / f"{chapter_id}_characters_final.json"
        self._save_json(char_path, final_chars)

        # Write chapter_info_final
        info_final = {
            "chapter_id": chapter_id,
            "segments": segments,
            "characters": final_chars,
        }
        info_path = self.work_dir / f"{chapter_id}_chapter_info_final.json"
        self._save_json(info_path, info_final)

        logger.debug("Final chapter files written for %s", chapter_id)
       
       
    # ------------------------------------------------------------------
    # PHASE 7 — TTS generation (per-segment, contract-compliant)
    # ------------------------------------------------------------------

    def tts_generate(self) -> None:
        """
        Phase 7:
        - Read chXXX_chapter_info_final.json (ChapterInfoFinal)
        - Generate per-segment WAVs: audio/chXXX/chXXX_segYYY.wav
        - Concatenate per-chapter WAV: audio/chXXX/chXXX.wav
        - Write audio_timing.json (AudioTimingMap)
        """
        logger.info("[Phase 7] Generating TTS audio…")

        # Load chapters.json to know how many chapters exist
        chapters = self._load_json(self.work_dir / "chapters.json", default=[])
        total = len(chapters)
        if total == 0:
            logger.warning("No chapters.json found — skipping TTS generation.")
            return

        # Build TTS backend (must implement TTSEngineContract)
        audio_root = self.work_dir / "audio"
        audio_root.mkdir(parents=True, exist_ok=True)
        engine = self._make_tts_backend(output_dir=str(audio_root))

        # Global timing map: chapter_id -> list[AudioTimingEntry]
        audio_timing: dict[str, list[dict]] = {}

        # Global TTS settings
        tts_speed = float(self.settings.get("tts_speed", 1.0))

        for idx in range(total):
            chapter_id = self._chapter_id(idx)
            final_info_path = self.work_dir / f"{chapter_id}_chapter_info_final.json"

            if not final_info_path.exists():
                logger.warning(
                    "Missing final chapter info for %s — skipping TTS for this chapter.",
                    chapter_id,
                )
                continue

            data = self._load_json(final_info_path, default={})
            segments = data.get("segments", [])
            if not segments:
                logger.warning("No segments found in %s — skipping.", final_info_path)
                continue

            logger.info("Generating audio for %s (%d/%d)…", chapter_id, idx + 1, total)

            chapter_audio_dir = audio_root / chapter_id
            chapter_audio_dir.mkdir(parents=True, exist_ok=True)

            segment_files: list[str] = []
            timing_entries: list[dict] = []

            current_time = 0.0  # seconds

            for seg_idx, seg in enumerate(segments):
                text = str(seg.get("text", "") or "").strip()
                if not text:
                    continue

                seg_type = str(seg.get("type", "narration") or "narration")
                speaker = str(seg.get("speaker", "narrator") or "narrator")
                gender = str(seg.get("gender", "unknown") or "unknown")

                # Resolve voice via VoiceRouter
                voice = self.voice_router.get_voice_for_segment(
                    speaker=speaker,
                    seg_type=seg_type,
                    gender=gender,
                )

                seg_filename = f"{chapter_id}_seg{seg_idx:03d}.wav"
                seg_path = chapter_audio_dir / seg_filename

                try:
                    engine.generate_audio(
                        text=text,
                        output_filename=str(seg_path),
                        voice=voice,
                        speed=tts_speed,
                    )
                    duration = float(engine.get_last_audio_duration() or 0.0)
                except Exception:
                    logger.error(
                        "TTS generation failed for %s segment %d",
                        chapter_id,
                        seg_idx,
                        exc_info=True,
                    )
                    continue

                # Record timing entry
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

            # Concatenate per-chapter audio
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

        # Save global audio timing map
        timing_path = self.work_dir / "audio_timing.json"
        self._save_json(timing_path, audio_timing)

        logger.info(
            "Phase 7 — TTS generation complete. %d chapters with timing data.",
            len(audio_timing),
        )

       
    # ------------------------------------------------------------------
    # PHASE 8 — EPUB build (EPUB3 + SMIL, contract-compliant)
    # ------------------------------------------------------------------

    def epub_build(self) -> None:
        """
        Phase 8:
        - Load final chapter info (chXXX_chapter_info_final.json)
        - Load audio_timing.json (AudioTimingMap)
        - Build per-chapter XHTML with per-segment <p id=paragraph_id>
        - Attach audio + timing via EPUBBuilder.add_audio()
        - Build final EPUB via EPUBBuilder.build()
        """
        logger.info("[Phase 8] Building EPUB…")

        # Load chapter inventory for titles
        chapters = self._load_json(self.work_dir / "chapters.json", default=[])
        total = len(chapters)
        if total == 0:
            logger.warning("No chapters.json found — cannot build EPUB.")
            return

        # Load audio timing map
        timing_path = self.work_dir / "audio_timing.json"
        audio_timing = self._load_json(timing_path, default={})
        if not audio_timing:
            logger.warning("audio_timing.json missing or empty — EPUB will have no media overlays.")

        # Book metadata
        title = str(self.settings.get("book_title", "Untitled Book") or "Untitled Book")
        author = str(self.settings.get("book_author", "Unknown Author") or "Unknown Author")

        # EPUB work dir (separate from general pipeline work_dir to keep things clean)
        epub_work_dir = self.work_dir / "epub_build"
        epub_work_dir.mkdir(parents=True, exist_ok=True)

        # Instantiate EPUBBuilder (implements EPUBBuilderContract)
        builder = EPUBBuilder(
            title=title,
            author=author,
            output_dir=self.settings.output_dir,
            work_dir=str(epub_work_dir),
        )

        # Helper: simple HTML escaping
        def _escape_html(text: str) -> str:
            return (
                text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
            )

        audio_root = self.work_dir / "audio"

        for idx, ch in enumerate(chapters):
            chapter_id = self._chapter_id(idx)
            final_info_path = self.work_dir / f"{chapter_id}_chapter_info_final.json"

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
                or ch.get("title")
                or f"Chapter {idx + 1}"
            )

            # Build XHTML with one <p> per semantic segment, id = paragraph_id
            body_parts: list[str] = []
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

            # Add chapter to EPUB
            builder.add_chapter(
                filename=chapter_filename,
                xhtml=xhtml,
                title=ch_title,
            )

            # Attach audio + timing if available
            chapter_audio_dir = audio_root / chapter_id
            chapter_audio_path = chapter_audio_dir / f"{chapter_id}.wav"

            timings_raw = audio_timing.get(chapter_id, [])
            if chapter_audio_path.exists() and timings_raw:
                ts_segments: list[TextSegment] = []
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

        # Build final EPUB
        epub_path = builder.build()
        logger.info("Phase 8 — EPUB build complete: %s", epub_path)
        self._on_progress("epub_build", 100)

    # ------------------------------------------------------------------
    # TTS Preview — upgraded to multi-speaker logic
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
        chapter_id = self._chapter_id(chapter_index)
        info_file = self.work_dir / f"{chapter_id}_chapter_info_final.json"

        if not info_file.exists():
            raise FileNotFoundError(f"chapter_info_final.json not found for {chapter_id}")

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

        seg_type = seg.get("type", "narration")
        speaker = seg.get("speaker", "narrator")
        gender = seg.get("gender", "unknown")

        # Voice selection
        voice_name = self.voice_router.get_voice_for_segment(
            speaker=speaker,
            seg_type=seg_type,
            gender=gender,
        )

        # Preview directory
        preview_dir = self.work_dir / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)

        engine = self._make_tts_backend(output_dir=str(preview_dir))
        out_path = preview_dir / f"{chapter_id}_seg{segment_index:03d}_preview.wav"

        logger.info(
            "TTS segment preview: chapter=%s, segment=%d, type=%s, speaker=%s, voice=%s",
            chapter_id,
            segment_index,
            seg_type,
            speaker,
            voice_name,
        )

        engine.generate_audio(
            text=text,
            output_filename=out_path.name,
            voice=voice_name,
            speed=self.settings.tts_speed,
        )

        return out_path