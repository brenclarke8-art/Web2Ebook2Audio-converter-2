# ebook_app/core/settings_manager.py
"""Persistent application settings manager.

Settings are stored as a flat JSON file in the user's app home directory.
All keys have sensible defaults defined in DEFAULTS.  Keys that are
no longer used by the application are stripped on load so the on-disk
file stays clean.
"""
from __future__ import annotations
import json
import logging
import os
from PySide6.QtCore import QObject, Signal

from ebook_app.utility.runtime_paths import APP_HOME_DIR, DEFAULT_SETTINGS_PATH

logger = logging.getLogger(__name__)


class SettingsManager(QObject):
    """Read/write persistent application settings with Qt signal support."""

    settings_changed = Signal(str)

    _LOG_GETS: bool = os.environ.get(
        "EBOOK_AUDIO_STUDIO_LOG_SETTINGS_GET", ""
    ).strip().lower() in {"1", "true", "yes", "on"}

    DEFAULTS: dict = {
        # ── UI / Window ──────────────────────────────────────────────────
        "theme": "dark",
        "window_width": 1200,
        "window_height": 800,

        # ── Output ───────────────────────────────────────────────────────
        "output_dir": str(APP_HOME_DIR.parent / "output"),

        # ── Pipeline mode ─────────────────────────────────────────────────
        # "manual"   → pause + diff display after every phase
        # "semi_auto"→ auto through phases 1-5b, pause at phase 6, then auto 7-8
        # "auto"     → run all phases and all chapters without pausing
        "pipeline_mode": "manual",

        # ── TTS backend ──────────────────────────────────────────────────
        "tts_backend_url": "http://127.0.0.1:5005",
        "tts_autostart_service": True,
        "tts_voice": "af_heart",
        "tts_speed": 1.0,
        "kokoro_model_path": "",
        "kokoro_voices_path": "",

        # ── Multi-speaker voice defaults ─────────────────────────────────
        "narrator_voice": "af_heart",
        "default_male_voice": "am_adam",
        "default_female_voice": "af_bella",

        # ── LLM ──────────────────────────────────────────────────────────
        "llm_provider": "ollama_local",
        "llm_url": "http://127.0.0.1:11434/api/chat",
        "llm_model": "qwen2.5-coder:7b",
        "llm_api_key": "",
        "llm_timeout": 300,
        "llm_retries": 1,
        "llm_preflight_check": True,
        "llm_batch_size": 20,
        "llm_chunk_size": 6000,
        "llm_chunk_overlap": 500,

        # ── Translation (Phase 3) ─────────────────────────────────────────
        "translation_enabled": False,
        "translation_target_language": "en",

        # ── Scraper ───────────────────────────────────────────────────────
        "scraper_method": "browser",
        "scraper_max_index_pages": 50,
        "scraper_browser_timeout_sec": 30,
        "scraper_wait_for_js": True,
        "scraper_remove_overlays": True,
        "scraper_browser_channel": "",
        "scraper_delay_ms": 500,
        "scraper_css_selectors": "",
        "scraper_exclude_selectors": "",

        # ── Character DB (project-level cache) ────────────────────────────
        "character_db": [],
    }

    # Keys that existed in earlier versions and are now fully removed.
    _OBSOLETE_KEYS: tuple[str, ...] = (
        # Legacy LLM aliases
        "dialogue_llm_url",
        "dialogue_llm_model",
        "dialogue_llm_timeout",
        "dialogue_llm_retries",
        "dialogue_llm_strict_quotes",
        "dialogue_llm_delimited_text_only",
        "dialogue_llm_delimiter_single_quotes",
        "dialogue_llm_delimiter_double_quotes",
        "dialogue_llm_delimiter_square_brackets",
        "dialogue_llm_delimiter_curly_braces",
        "dialogue_llm_delimiter_angle_brackets",
        "dialogue_llm_delimiter_parentheses",
        "dialogue_llm_batch_size",
        "dialogue_llm_protocol_retries",
        # Old pipeline-review knobs
        "clean_review_mode",
        "clean_review_sample_chapters",
        "dialogue_review_mode",
        "speaker_conf_threshold",
        "character_conf_threshold",
        # Internal implementation details
        "llm_segment_mode",
        "llm_fallback_failure_threshold",
        "json_pipeline_enabled",
        "json_repair_max_retries",
        "phase1_llm_assist_enabled",
        "phase2_batch_size",
        # Transient / moved to project state
        "character_review_approved",
        "pending_character_additions",
        # Scraper options no longer exposed
        "scraper_use_browser_gui",
        "scraper_manual_navigation",
        "scraper_manual_navigation_timeout_sec",
        # Very old keys
        "tts_backend_mode",
        "llm_api_url",
        "ollama_url",
        "ollama_model",
        "audio_output_mode",
        "multispeaker_enabled",
        "dialogue_llm_mode",
        "dialogue_llm_semantic_model",
        "dialogue_llm_formatter_model",
        "story_context_enabled",
        "index_url",
        "character_confidence_threshold",
    )

    def __init__(self) -> None:
        super().__init__()
        APP_HOME_DIR.mkdir(parents=True, exist_ok=True)
        self.path = DEFAULT_SETTINGS_PATH
        self.settings_path = self.path  # backward-compat alias
        self.data: dict = {}
        self._settings = self.data  # backward-compat alias
        self.load()

    # ─────────────────────────────────────────────────────────────────────
    # Load / Save
    # ─────────────────────────────────────────────────────────────────────

    def load(self) -> None:
        logger.debug("Loading settings from %s", self.path)
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    self.data = json.load(fh)
            except Exception:
                self.data = {}
        else:
            self.data = {}

        # Migrate: promote legacy llm_url / llm_model before removing old keys
        self._migrate_llm_keys()

        # Apply defaults for any missing key
        changed = False
        for key, value in self.DEFAULTS.items():
            if key not in self.data:
                self.data[key] = value
                changed = True

        # Remove obsolete keys
        for key in self._OBSOLETE_KEYS:
            if key in self.data:
                self.data.pop(key)
                changed = True

        self._settings = self.data
        if changed:
            self.save()

    def _migrate_llm_keys(self) -> None:
        """Promote dialogue_llm_* legacy values into the canonical llm_* keys."""
        if not self.data.get("llm_url"):
            legacy = self.data.get("dialogue_llm_url", "")
            if legacy:
                self.data["llm_url"] = legacy
        if not self.data.get("llm_model"):
            legacy = self.data.get("dialogue_llm_model", "")
            if legacy:
                self.data["llm_model"] = legacy
        if not self.data.get("llm_timeout"):
            legacy = self.data.get("dialogue_llm_timeout")
            if legacy:
                self.data["llm_timeout"] = legacy
        if not self.data.get("llm_retries"):
            legacy = self.data.get("dialogue_llm_retries")
            if legacy:
                self.data["llm_retries"] = legacy
        if not self.data.get("llm_batch_size"):
            legacy = self.data.get("phase2_batch_size") or self.data.get("dialogue_llm_batch_size")
            if legacy:
                self.data["llm_batch_size"] = legacy

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2)
        except Exception as exc:
            logger.error("Failed to save settings: %s", exc)

    # ─────────────────────────────────────────────────────────────────────
    # Get / Set
    # ─────────────────────────────────────────────────────────────────────

    def get(self, key: str, default=None):
        value = self.data.get(key, default)
        if self._LOG_GETS:
            logger.debug("Settings get: %s=%r", key, value)
        return value

    def set(self, key: str, value) -> None:
        logger.debug("Settings set: %s=%r", key, value)
        self.data[key] = value
        self.save()
        self.settings_changed.emit(key)

    # ─────────────────────────────────────────────────────────────────────
    # Convenience properties
    # ─────────────────────────────────────────────────────────────────────

    @property
    def pipeline_mode(self) -> str:
        return self.get("pipeline_mode", "manual")

    @pipeline_mode.setter
    def pipeline_mode(self, value: str) -> None:
        self.set("pipeline_mode", value)

    @property
    def tts_voice(self) -> str:
        return self.get("tts_voice")

    @tts_voice.setter
    def tts_voice(self, value: str) -> None:
        self.set("tts_voice", value)

    @property
    def tts_speed(self) -> float:
        return self.get("tts_speed")

    @tts_speed.setter
    def tts_speed(self, value: float) -> None:
        self.set("tts_speed", value)

    @property
    def kokoro_model_path(self) -> str:
        return self.get("kokoro_model_path")

    @kokoro_model_path.setter
    def kokoro_model_path(self, value: str) -> None:
        self.set("kokoro_model_path", value)

    @property
    def kokoro_voices_path(self) -> str:
        return self.get("kokoro_voices_path")

    @kokoro_voices_path.setter
    def kokoro_voices_path(self, value: str) -> None:
        self.set("kokoro_voices_path", value)

    @property
    def tts_backend_url(self) -> str:
        return self.get("tts_backend_url")

    @tts_backend_url.setter
    def tts_backend_url(self, value: str) -> None:
        self.set("tts_backend_url", value)

    @property
    def tts_autostart_service(self) -> bool:
        return self.get("tts_autostart_service")

    @tts_autostart_service.setter
    def tts_autostart_service(self, value: bool) -> None:
        self.set("tts_autostart_service", value)

    @property
    def output_dir(self) -> str:
        return self.get("output_dir")

    @output_dir.setter
    def output_dir(self, value: str) -> None:
        self.set("output_dir", value)

    @property
    def theme(self) -> str:
        return self.get("theme")

    @theme.setter
    def theme(self, value: str) -> None:
        self.set("theme", value)
