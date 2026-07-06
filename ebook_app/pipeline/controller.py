# ebook_app/pipeline/controller.py
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ebook_app.app.state.character_db import CharacterDatabase
from ebook_app.text.identify.role_tagger import Pass1Extractor
from ebook_app.text.identify.type_classifier import Pass2Classifier, LLMClient
from ebook_app.tts.voice_router import VoiceRouter
from ebook_app.pipeline.chapter_rebuilder import ChapterRebuilder
from ebook_app.epub.packaging import EPUBBuilder
from ebook_app.tts.tts_service import TTSEngineContract

try:
    from ebook_app.text.scrape.browser_scraper import WebScraper as WebScraper  # noqa: F401
except ImportError:  # pragma: no cover
    WebScraper = None  # type: ignore

def _obj_to_dict(obj: Any) -> Dict:
    """Convert a dataclass or namespace object to a plain dict."""
    if hasattr(obj, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(obj)
    if hasattr(obj, "__dict__"):
        return vars(obj)
    return dict(obj)  # type: ignore


logger = logging.getLogger(__name__)
MIN_LLM_TIMEOUT_SEC = 1
MIN_LLM_RETRIES = 0


def _int_setting(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool_setting(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _gs(settings: Any, *keys: str, default: Any = "") -> Any:
    """Return the first non-None value found by direct attribute or .get() on settings."""
    for key in keys:
        v = getattr(settings, key, None)
        if v is not None:
            return v
    if hasattr(settings, "get"):
        for key in keys:
            v = settings.get(key, None)
            if v is not None:
                return v
    return default


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
        llm_provider: str = "ollama_local",
        llm_api_key: str = "",
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
        self.llm_provider = llm_provider
        self.llm_api_key = llm_api_key
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

    STEPS: List[str] = [
        "scrape_index",
        "scrape_chapters",
        "pass1_extraction",
        "pass2_classification",
        "smart_review_dialogue",
        "tts_generate",
        "epub_build",
    ]

    def __init__(
        self,
        settings: Any,
        work_dir: Optional[Path] = None,
    ) -> None:
        self.settings = settings

        # work_dir: prefer explicit arg, then settings.work_dir, then fallback
        if work_dir is not None:
            self.work_dir = Path(work_dir)
        else:
            wd = getattr(settings, "work_dir", None)
            self.work_dir = Path(wd) if wd else Path("pipeline_work")

        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Chapter state
        self.selected_start_chapter: int = 1
        self.selected_end_chapter: int = 0
        self.chapters: List[Dict] = []
        self.raw_chapter_urls: List[str] = []
        self.chapter_urls: List[str] = []

        self.character_db = CharacterDatabase(
            path=self.work_dir / "character_database.json"
        )

        # Voice routing + chapter rebuild helpers
        narrator = _gs(settings, "narrator_voice", default="af_narrator")
        default_male = _gs(settings, "default_male_voice", default="am_adam")
        default_female = _gs(settings, "default_female_voice", default="af_heart")
        self.voice_router = VoiceRouter(
            narrator_voice=narrator,
            default_male_voice=default_male,
            default_female_voice=default_female,
        )
        self.chapter_rebuilder = ChapterRebuilder(self.voice_router)

        # LLM client + Pass‑2 classifier
        llm_url = _gs(settings, "llm_url", "llm_base_url", "dialogue_llm_url", default="")
        llm_model = _gs(settings, "llm_model", "dialogue_llm_model", default="")
        llm_provider = _gs(settings, "llm_provider", default="ollama_local")
        llm_api_key = _gs(settings, "llm_api_key", default="")
        phase2_batch_size = int(_gs(settings, "phase2_batch_size", default=20) or 20)
        llm_timeout = _int_setting(_gs(settings, "llm_timeout", "dialogue_llm_timeout", default=None), 300)
        llm_retries = _int_setting(_gs(settings, "llm_retries", "dialogue_llm_retries", default=None), 1)
        json_pipeline_enabled = _bool_setting(
            os.environ.get("JSON_PIPELINE_ENABLED"),
            _bool_setting(_gs(settings, "json_pipeline_enabled", default=True), True),
        )
        json_repair_max_retries = _int_setting(
            os.environ.get("JSON_REPAIR_MAX_RETRIES"),
            _int_setting(_gs(settings, "json_repair_max_retries", default=2), 2),
        )
        llm_segment_mode = (
            str(os.environ.get("LLM_SEGMENT_MODE", "")).strip().lower()
            or str(_gs(settings, "llm_segment_mode", default="batch")).strip().lower()
            or "batch"
        )
        llm_fallback_failure_threshold = _int_setting(
            os.environ.get("LLM_FALLBACK_FAILURE_THRESHOLD"),
            _int_setting(_gs(settings, "llm_fallback_failure_threshold", default=2), 2),
        )
        # Write per-request LLM call logs next to the other pipeline work files.
        llm_log_path = str(self.work_dir / "llm_calls.jsonl")
        self.llm_client = LLMClient(
            base_url=llm_url,
            model=llm_model,
            timeout=max(MIN_LLM_TIMEOUT_SEC, llm_timeout),
            retries=max(MIN_LLM_RETRIES, llm_retries),
            provider=llm_provider,
            api_key=llm_api_key,
            llm_log_path=llm_log_path,
        )
        self.pass2_classifier = Pass2Classifier(
            self.llm_client,
            batch_size=phase2_batch_size,
            json_pipeline_enabled=json_pipeline_enabled,
            json_repair_max_retries=json_repair_max_retries,
            segment_mode=llm_segment_mode,
            fallback_failure_threshold=llm_fallback_failure_threshold,
        )

        # Cancellation + progress callbacks
        self._cancel_flags: Dict[str, bool] = {}
        self._progress_callback = None
        self._conversation_callback = None

    # ------------------------------------------------------------------
    # Lifecycle: start / stop / run_all
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Reset all cancellation flags so the pipeline can run."""
        self._cancel_flags = {}

    def stop(self) -> None:
        """Request cancellation of all phases."""
        for step in self.STEPS:
            self._cancel_flags[step] = True

    def set_chapter_range(self, start: int, end: int) -> None:
        """Set the inclusive 1-based chapter range to process."""
        self.selected_start_chapter = start
        self.selected_end_chapter = end

    def run_all(self) -> None:
        """Execute every pipeline step in order."""
        for step in self.STEPS:
            getattr(self, step)()

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
        return f"ch{offset + 1}"

    def _chapter_cleaned_text_path(self, chapter_id: str) -> Path:
        return self.work_dir / f"{chapter_id}_cleaned.txt"

    def _chapter_raw_text_path(self, chapter_id: str) -> Path:
        return self.work_dir / f"{chapter_id}_raw.txt"

    def _chapter_pass1_path(self, chapter_id: str) -> Path:
        return self.work_dir / f"{chapter_id}_pass1.json"

    def _chapter_pass2_path(self, chapter_id: str) -> Path:
        return self.work_dir / f"{chapter_id}_pass2.json"

    def _chapter_final_path(self, chapter_id: str) -> Path:
        return self.work_dir / f"{chapter_id}_final.json"

    def _chapter_info_final_path(self, chapter_id: str) -> Path:
        return self.work_dir / f"{chapter_id}_chapter_info_final.json"

    def _chapter_llm_raw_path(self, chapter_id: str) -> Path:
        return self.work_dir / f"{chapter_id}_llm_raw.json"

    def _chapter_llm_normalized_path(self, chapter_id: str) -> Path:
        return self.work_dir / f"{chapter_id}_llm_normalized.json"

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

    def set_conversation_callback(self, cb) -> None:
        """Set a callback(role: str, content: str) called for each LLM request/response."""
        self._conversation_callback = cb

    # ------------------------------------------------------------------
    # Phase 1 — scrape_index (web scraping to get chapter list)
    # ------------------------------------------------------------------

    def scrape_index(self) -> None:
        """
        Phase 1:
        - Scrape the chapter index using WebScraper
        - Filter placeholder/paywalled URLs
        - Write chapters_raw.json, raw_chapter_urls.json, chapter_urls.json
        """
        logger.info("[Phase 1] Scraping index…")

        index_url = _gs(self.settings, "index_url", default="")
        if not index_url:
            logger.warning("No index URL configured — cannot scrape index.")
            self._on_progress("scrape_index", 100)
            return

        scraper = WebScraper()
        try:
            all_urls = list(scraper.scrape_index_page(index_url))
        except Exception:
            logger.error("Index scraping failed.", exc_info=True)
            all_urls = []

        self.raw_chapter_urls = [str(u) for u in all_urls]
        self.chapter_urls = [u for u in self.raw_chapter_urls if "paywalled" not in u]

        # Normalize into a list of dicts for legacy pipeline worker
        normalized = [
            {"title": f"Chapter {i + 1}", "source": url}
            for i, url in enumerate(self.chapter_urls)
        ]

        self._save_json(self.work_dir / "chapters_raw.json", normalized)
        self._save_json(self.work_dir / "raw_chapter_urls.json", self.raw_chapter_urls)
        self._save_json(self.work_dir / "chapter_urls.json", self.chapter_urls)

        logger.info(
            "Index scraped: %d total, %d valid chapters.",
            len(self.raw_chapter_urls),
            len(self.chapter_urls),
        )
        self._on_progress("scrape_index", 100)


    # ------------------------------------------------------------------
    # Phase 2 — scrape_chapters (per-chapter scraping + cleaning)
    # ------------------------------------------------------------------

    def scrape_chapters(
        self,
        *,
        chapter_progress_callback: Optional[Any] = None,
    ) -> None:
        """
        Phase 2:
        - Select URLs based on chapter range + self.chapter_urls
        - Batch-scrape with WebScraper.scrape_chapters()
        - Write chN_raw.txt and chN_cleaned.txt for each chapter
        - Set self.chapters with scraped data

        Args:
            chapter_progress_callback: Optional callable(current, total, url) called
                after each chapter is fetched. Receives 1-based current index, total
                count, and the URL just scraped.
        """
        logger.info("[Phase 2] Scraping chapters…")

        from ebook_app.text.parse.html_cleaner import TextCleaner

        # When chapter_urls has been set externally (e.g. from the UI's selected
        # checkboxes) it already contains exactly the URLs to scrape — do NOT
        # re-apply the start/end chapter range, as that would slice the list a
        # second time and skip chapters.  When chapter_urls is empty we fall back
        # to chapters_raw.json and apply the range there.
        if self.chapter_urls:
            selected_urls = list(self.chapter_urls)
            # chapter_offset: 1-based index of the first URL in the file-naming
            # scheme so that ch<N>_raw.txt reflects the right chapter number.
            chapter_offset = self.selected_start_chapter
        else:
            chapters_raw = self._load_json(self.work_dir / "chapters_raw.json", default=[])
            all_urls = [ch.get("source", "") for ch in chapters_raw if ch.get("source")]
            start_idx = self.selected_start_chapter - 1
            end_idx = self.selected_end_chapter if self.selected_end_chapter > 0 else len(all_urls)
            selected_urls = all_urls[start_idx:end_idx]
            chapter_offset = self.selected_start_chapter

        if not selected_urls:
            logger.warning("No chapter URLs — cannot scrape chapters.")
            return

        self.work_dir.mkdir(parents=True, exist_ok=True)
        scraper = WebScraper()

        # Wrap the caller's callback so we can also emit it from inside
        # WebScraper (which already supports a progress_callback).
        def _progress(current: int, total: int, url: str) -> None:
            logger.info("Scraping chapter %d/%d: %s", current, total, url)
            if callable(chapter_progress_callback):
                try:
                    chapter_progress_callback(current, total, url)
                except Exception:
                    pass

        try:
            results = scraper.scrape_chapters(selected_urls, progress_callback=_progress)
        except Exception:
            logger.error("Chapter scraping failed.", exc_info=True)
            results = []

        self.chapters = []
        for idx, result in enumerate(results):
            if self._cancelled("scrape_chapters"):
                return

            chapter_id = f"ch{chapter_offset + idx}"
            content = result.get("content", "") or ""
            title = result.get("title", f"Chapter {chapter_offset + idx}")

            raw_path = self._chapter_raw_text_path(chapter_id)
            raw_path.write_text(content, encoding="utf-8")

            cleaned = TextCleaner.clean_text(content)
            self._chapter_cleaned_text_path(chapter_id).write_text(cleaned, encoding="utf-8")

            self.chapters.append({"title": title, "content": content})
            logger.info("Scraped %s", chapter_id)

        logger.info("Phase 2 — scrape_chapters complete.")
        self._on_progress("scrape_chapters", 100)

    # ------------------------------------------------------------------
    # Phase 2b — clean_chapters (noise + zero-width char removal)
    # ------------------------------------------------------------------

    def clean_chapters(self) -> None:
        """
        Clean self.chapters in-memory and write chN_cleaned.txt.
        Removes UI noise lines ("Next Chapter", "Subscribe now") and
        zero-width characters.
        """
        logger.info("clean_chapters: cleaning %d chapters…", len(self.chapters))
        NOISE_LINES = {"next chapter", "subscribe now"}
        ZERO_WIDTH = "\u200b\u200c\u200d\ufeff"

        self.work_dir.mkdir(parents=True, exist_ok=True)
        for idx, ch in enumerate(self.chapters):
            chapter_id = f"ch{self.selected_start_chapter + idx}"
            content = ch.get("content", "") or ""

            for char in ZERO_WIDTH:
                content = content.replace(char, "")

            lines = [
                line for line in content.splitlines()
                if line.strip().casefold() not in NOISE_LINES
            ]
            cleaned = "\n".join(lines)

            self._chapter_cleaned_text_path(chapter_id).write_text(cleaned, encoding="utf-8")
            logger.info("clean_chapters: wrote %s_cleaned.txt", chapter_id)

        logger.info("clean_chapters complete.")


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
        llm_assist_enabled = bool(_gs(self.settings, "phase1_llm_assist_enabled", default=False))

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
            if llm_assist_enabled and segments:
                try:
                    segments = self.pass2_classifier.assist_pass1_segments(segments, chapter_id=chapter_id)
                except Exception:
                    logger.error("Phase-1 LLM assist failed for %s", chapter_id, exc_info=True)

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

            if self._cancelled("pass2_classification"):
                return
            try:
                classified = self.pass2_classifier.classify_segments(
                    segments,
                    chapter_id=chapter_id,
                    should_cancel=lambda: self._cancelled("pass2_classification"),
                    on_conversation=self._conversation_callback,
                )
            except Exception:
                logger.error("Pass‑2 batched classification failed for %s", chapter_id, exc_info=True)
                classified = [
                    {
                        "text": str(seg.get("text", "")),
                        "type": "narration",
                        "speaker": "narrator",
                        "gender": "unknown",
                        "speaker_confidence": 0.0,
                        "gender_confidence": 0.0,
                        "character_confidence": 0.0,
                        "paragraph_id": str(seg.get("paragraph_id", "")),
                        "voice": str(seg.get("voice", "")),
                        "emotion": str(seg.get("emotion", "neutral") or "neutral"),
                        "prior_segment_text": str(seg.get("context_before", "")),
                        "next_segment_text": str(seg.get("context_after", "")),
                    }
                    for seg in segments
                ]
            if self._cancelled("pass2_classification"):
                return



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

    # ------------------------------------------------------------------
    # LLM helpers (dialogue parsing)
    # ------------------------------------------------------------------

    def _build_dialogue_parser(self):
        """Build a DialogueParser using current settings."""
        from ebook_app.text.identify.speaker_llm import DialogueParser

        url = _gs(
            self.settings,
            "llm_url",
            "dialogue_llm_url",
            "dialogue_llm_base_url",
            "llm_base_url",
            default="http://127.0.0.1:11434/api/chat",
        )
        base_model = _gs(self.settings, "llm_model", "dialogue_llm_model", default="") or None
        return DialogueParser(
            ollama_url=url,
            model=base_model,
        )

    def _preflight_llm_check(self, parser) -> None:
        """Check that the model used by *parser* is installed in Ollama."""
        import requests

        base_url = getattr(parser, "ollama_url", "")
        for suffix in ("/api/generate", "/api/chat"):
            if base_url.endswith(suffix):
                base_url = base_url[: -len(suffix)]
                break
        tags_url = base_url.rstrip("/") + "/api/tags"
        resp = requests.get(tags_url)
        resp.raise_for_status()
        installed_names = [m.get("name", "") for m in resp.json().get("models", [])]
        # Normalize by stripping the tag suffix (e.g. "mistral:instruct" → "mistral")
        # to match the behaviour of the UI health check.
        installed_normalized = {(n or "").split(":", 1)[0].strip().lower() for n in installed_names}
        model = getattr(parser, "model", "")
        model_normalized = (model or "").split(":", 1)[0].strip().lower()
        if model_normalized not in installed_normalized:
            raise RuntimeError(
                f"Ollama model '{model}' is not installed. "
                "Install it with: ollama pull " + model
            )

    def llm_semantic_analysis(self) -> None:
        """
        Run dialogue parsing on each cleaned chapter and write chN_llm_raw.json.
        """
        logger.info("llm_semantic_analysis: starting…")

        chapters = (
            self._load_json(self.work_dir / "chapters.json", default=None)
            or self._load_json(self.work_dir / "chapters_raw.json", default=[])
        )
        total = len(chapters)
        if total == 0:
            logger.warning("No chapters found — cannot run LLM semantic analysis.")
            return

        for idx in range(total):
            chapter_id = f"ch{self.selected_start_chapter + idx}"
            cleaned_path = self._chapter_cleaned_text_path(chapter_id)
            if not cleaned_path.exists():
                logger.warning("Missing cleaned text for %s — skipping.", chapter_id)
                continue

            text = cleaned_path.read_text(encoding="utf-8")
            parser = self._build_dialogue_parser()
            result = parser.parse(text, chapter_id)

            raw_data = {
                "segments": [_obj_to_dict(s) for s in result.segments],
                "detected_characters": [_obj_to_dict(c) for c in result.detected_characters],
            }
            self._save_json(self._chapter_llm_raw_path(chapter_id), raw_data)
            logger.info("llm_semantic_analysis: wrote %s_llm_raw.json", chapter_id)

        logger.info("llm_semantic_analysis complete.")

    def _write_final_chapter_files(
        self,
        chapter_id: str,
        segments: List[Dict],
        detected_chars: List[Dict],
        narrator_voice: str,
        default_male: str,
        default_female: str,
        character_db: Any,
    ) -> None:
        """
        Assign voices to characters and write chN_chapter_info_final.json.
        *character_db* may be a list of dicts or a CharacterDatabase object.
        Unknown characters are added to *character_db* with their assigned voice.
        """
        def _lookup_voice(name: str) -> Optional[str]:
            if isinstance(character_db, list):
                norm = name.strip().casefold()
                for entry in character_db:
                    if entry.get("name", "").strip().casefold() == norm:
                        return entry.get("voice") or None
                return None
            # CharacterDatabase object
            c = character_db.get(name)
            return c.voice if c and c.voice else None

        def _add_to_db(name: str, gender: str, voice: str) -> None:
            if isinstance(character_db, list):
                character_db.append(
                    {"name": name, "gender": gender, "voice": voice, "description": ""}
                )
            else:
                character_db.add_or_update(name, gender=gender, voice=voice)

        final_chars: List[Dict] = []
        seen_names: set = set()
        for entry in detected_chars:
            name = entry.get("name", "")
            gender = entry.get("gender", "unknown")
            if not name or name.strip().casefold() in seen_names:
                continue
            seen_names.add(name.strip().casefold())
            voice = _lookup_voice(name)
            if not voice:
                voice = default_male if gender == "male" else (
                    default_female if gender == "female" else narrator_voice
                )
                _add_to_db(name, gender, voice)
            final_chars.append({"name": name, "gender": gender, "voice": voice})

        out = {"characters": final_chars, "segments": segments}
        self._save_json(self._chapter_info_final_path(chapter_id), out)
        logger.info("_write_final_chapter_files: wrote %s_chapter_info_final.json", chapter_id)

    def recheck_dialogue_with_manual_context(
        self,
        chapter_id: str,
        hints: List[Dict],
    ) -> Dict:
        """
        Re-run dialogue parsing for *chapter_id* with manual segment hints and
        overwrite the LLM output files.
        Returns {"chapter_id": ..., "segment_count": ..., "character_count": ...}.
        """
        cleaned_path = self._chapter_cleaned_text_path(chapter_id)
        text = cleaned_path.read_text(encoding="utf-8") if cleaned_path.exists() else ""

        parser = self._build_dialogue_parser()
        result = parser.parse(text, chapter_id, manual_segment_hints=hints)

        raw_data = {
            "segments": [_obj_to_dict(s) for s in result.segments],
            "detected_characters": [_obj_to_dict(c) for c in result.detected_characters],
        }
        self._save_json(self._chapter_llm_raw_path(chapter_id), raw_data)
        self._save_json(self._chapter_llm_normalized_path(chapter_id), raw_data)

        return {
            "chapter_id": chapter_id,
            "segment_count": len(result.segments),
            "character_count": len(result.detected_characters),
        }

    def _make_tts_backend(self, output_dir: Optional[str] = None) -> TTSEngineContract:
        """
        Build a TTS backend instance.
        This must be implemented to return an object that satisfies TTSEngineContract.
        """
        raise NotImplementedError("_make_tts_backend must be implemented.")

    def tts_generate(self) -> None:
        """
        Phase 6:
        - Read chXXX_chapter_info_final.json (falls back to chXXX_final.json)
        - Generate per-segment WAVs: audio/chXXX/chXXX_segYYY.wav
        - Concatenate per-chapter WAV: audio/chXXX/chXXX.wav
        - Write audio_timing.json
        """
        logger.info("[Phase 6] Generating TTS audio…")

        chapters = (
            self._load_json(self.work_dir / "chapters.json", default=None)
            or self._load_json(self.work_dir / "chapters_raw.json", default=[])
        )
        total = len(chapters)
        if total == 0:
            logger.warning("No chapters file found — skipping TTS generation.")
            return

        audio_root = self.work_dir / "audio"
        audio_root.mkdir(parents=True, exist_ok=True)
        engine = self._make_tts_backend(output_dir=str(audio_root))

        audio_timing: Dict[str, List[Dict]] = {}
        tts_speed = float(_gs(self.settings, "tts_speed", default=1.0) or 1.0)

        for idx in range(total):
            if self._cancelled("tts_generate"):
                return

            chapter_id = f"ch{self.selected_start_chapter + idx}"
            # Try chapter_info_final first (new format), fall back to legacy _final.json
            final_info_path = self._chapter_info_final_path(chapter_id)
            if not final_info_path.exists():
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
