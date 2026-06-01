from __future__ import annotations
import json
import logging
import os
from pathlib import Path
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


def _default_app_home() -> Path:
    """Resolve repository-local runtime home (overridable via env var)."""
    env_home = os.environ.get("EBOOK_AUDIO_STUDIO_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src" / "ebook_app").exists():
            return parent / ".ebook_audio_studio"
    logger.warning(
        "Repository root could not be detected from %s; falling back to current working directory.",
        here,
    )
    return (Path.cwd() / ".ebook_audio_studio").resolve()


APP_HOME_DIR = _default_app_home().resolve()
DEFAULT_SETTINGS_PATH = APP_HOME_DIR / "settings.json"


class SettingsManager(QObject):
    settings_changed = Signal(str)
    _LOG_GETS = os.environ.get("EBOOK_AUDIO_STUDIO_LOG_SETTINGS_GET", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    DEFAULTS = {
        # ------------------------------
        # UI + Window
        # ------------------------------
        "theme": "dark",
        "window_width": 1200,
        "window_height": 800,

        # ------------------------------
        # Output
        # ------------------------------
        "output_dir": str(APP_HOME_DIR.parent / "output"),

        # ------------------------------
        # TTS Backend (remote-only)
        # ------------------------------
        "tts_backend_url": "http://127.0.0.1:5005",
        "tts_autostart_service": False,

        # Default single-voice TTS
        "tts_voice": "af_heart",
        "tts_speed": 1.0,

        # Kokoro local model paths (unused in remote mode)
        "kokoro_model_path": "",
        "kokoro_voices_path": "",

        # ------------------------------
        # LLM / Dialogue Parsing
        # ------------------------------
        "index_url": "",
        "dialogue_llm_mode": "full",
        "dialogue_llm_url": "http://127.0.0.1:11434/api/chat",
        "dialogue_llm_model": "mistral:instruct",
        "dialogue_llm_timeout": 120,
        "dialogue_llm_retries": 1,
        "dialogue_llm_strict_quotes": False,
        "llm_preflight_check": True,

        # ------------------------------
        # Character Confidence
        # ------------------------------
        "character_confidence_threshold": 0.8,
        "character_review_approved": False,

        # ------------------------------
        # Scraper
        # ------------------------------
        "scraper_method": "browser",
        "scraper_use_browser_gui": False,
        "scraper_manual_navigation": False,
        "scraper_manual_navigation_timeout_sec": 120,
        "scraper_max_index_pages": 50,
        "scraper_browser_timeout_sec": 30,
        "scraper_wait_for_js": True,
        "scraper_remove_overlays": True,
        "scraper_browser_channel": "",
        "scraper_delay_ms": 500,
        "scraper_css_selectors": "",
        "scraper_exclude_selectors": "",

        # ------------------------------
        # Multi-speaker TTS
        # ------------------------------
        "narrator_voice": "af_heart",
        "default_male_voice": "am_adam",
        "default_female_voice": "af_heart",

        # Character DB + pending additions
        "character_db": [],
        "pending_character_additions": [],

        # ------------------------------
        # NEW PIPELINE SETTINGS
        # ------------------------------

        # Phase 4 — Cleaned Text Review
        "clean_review_mode": "semi",              # skip | semi | full
        "clean_review_sample_chapters": 3,        # N chapters for semi mode

        # Phase 6 — Smart Dialogue Review
        "dialogue_review_mode": "smart",          # smart | always
        "speaker_conf_threshold": 0.8,
        "character_conf_threshold": 0.8,
    }

    def __init__(self):
        super().__init__()
        APP_HOME_DIR.mkdir(parents=True, exist_ok=True)
        self.path = DEFAULT_SETTINGS_PATH
        self.data = {}
        self.settings_path = self.path
        self._settings = self.data
        self.load()

    # ---------------------------------------------------------
    # Load / Save
    # ---------------------------------------------------------

    def load(self):
        logger.debug("Loading settings from %s", self.path)
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}
        else:
            self.data = {}

        # Apply defaults
        changed = False
        for key, value in self.DEFAULTS.items():
            if key not in self.data:
            self.data[key] = value
            changed = True

        for legacy_key in (
            "tts_backend_mode",
            "llm_api_url",
            "llm_api_key",
            "ollama_url",
            "ollama_model",
            "audio_output_mode",
            "multispeaker_enabled",
        ):
            if legacy_key in self.data:
            self.data.pop(legacy_key, None)
            changed = True

        self._settings = self.data
        if changed:
            self.save()

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print("Failed to save settings:", e)

    # ---------------------------------------------------------
    # Get / Set
    # ---------------------------------------------------------

    def get(self, key: str, default=None):
        value = self.data.get(key, default)
        if self._LOG_GETS:
            logger.debug("Settings get: %s=%r", key, value)
        return value

    def set(self, key: str, value):
        logger.debug("Settings set: %s=%r", key, value)
        self.data[key] = value
        self.save()
        self.settings_changed.emit(key)

    # ---------------------------------------------------------
    # Convenience Properties
    # ---------------------------------------------------------

    @property
    def tts_voice(self):
        return self.get("tts_voice")

    @tts_voice.setter
    def tts_voice(self, value):
        self.set("tts_voice", value)

    @property
    def tts_speed(self):
        return self.get("tts_speed")

    @tts_speed.setter
    def tts_speed(self, value):
        self.set("tts_speed", value)

    @property
    def kokoro_model_path(self):
        return self.get("kokoro_model_path")

    @kokoro_model_path.setter
    def kokoro_model_path(self, value):
        self.set("kokoro_model_path", value)

    @property
    def kokoro_voices_path(self):
        return self.get("kokoro_voices_path")

    @kokoro_voices_path.setter
    def kokoro_voices_path(self, value):
        self.set("kokoro_voices_path", value)

    @property
    def tts_backend_url(self):
        return self.get("tts_backend_url")

    @tts_backend_url.setter
    def tts_backend_url(self, value):
        self.set("tts_backend_url", value)

    @property
    def tts_autostart_service(self):
        return self.get("tts_autostart_service")

    @tts_autostart_service.setter
    def tts_autostart_service(self, value):
        self.set("tts_autostart_service", value)

    @property
    def output_dir(self):
        return self.get("output_dir")

    @output_dir.setter
    def output_dir(self, value):
        self.set("output_dir", value)

    @property
    def theme(self):
        return self.get("theme")

    @theme.setter
    def theme(self, value):
        self.set("theme", value)
