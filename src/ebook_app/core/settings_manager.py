from __future__ import annotations
import os
import json
import logging
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
        "tts_voice": "af_heart",
        "tts_speed": 1.0,
        "kokoro_model_path": "",
        "kokoro_voices_path": "",
        "output_dir": str(APP_HOME_DIR.parent / "output"),
        "theme": "dark",
        "window_width": 1200,
        "window_height": 800,
        # TTS backend is remote-only: GUI calls tts_service/tts_server.py via HTTP.
        "tts_backend_mode": "remote",
        "tts_backend_url": "http://127.0.0.1:5005",
        "tts_autostart_service": False,
        # LLM / translation API connection
        "llm_api_url": "http://localhost:5000/translate",
        "llm_api_key": "",
        "index_url": "",
        "ollama_url": "http://127.0.0.1:11434/api/generate",
        "ollama_model": "mistral",
        "character_confidence_threshold": 0.8,
        "character_review_approved": False,
        "audio_output_mode": "per_chapter",
        # Browser scraper controls
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
        # Multi-speaker TTS
        "multispeaker_enabled": False,
        "narrator_voice": "af_heart",
        "default_male_voice": "am_adam",
        "default_female_voice": "af_heart",
        # Character database: list of {name, voice, gender, description} dicts
        "character_db": [],
        # Suggested entries from parser to review in Settings UI.
        "pending_character_additions": [],
    }

    def __init__(self):
        super().__init__()
        APP_HOME_DIR.mkdir(parents=True, exist_ok=True)
        self.path = DEFAULT_SETTINGS_PATH
        self.data = {}
        # Backward-compatible aliases
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

        # Apply defaults for missing keys
        changed = False
        for key, value in self.DEFAULTS.items():
            if key not in self.data:
                self.data[key] = value
                changed = True
        if self.data.get("tts_backend_mode") != "remote":
            if "tts_backend_mode" in self.data:
                logger.info(
                    "Overriding tts_backend_mode=%r to 'remote' (remote-only mode).",
                    self.data.get("tts_backend_mode"),
                )
            self.data["tts_backend_mode"] = "remote"
            changed = True

        self._settings = self.data
        if changed:
            logger.debug("Settings were missing keys or needed migration; persisting defaults.")
            self.save()

    def save(self):
        try:
            logger.debug("Saving settings to %s", self.path)
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
    def tts_backend_mode(self):
        """Return 'local' (direct kokoro-onnx import) or 'remote' (HTTP service)."""
        return self.get("tts_backend_mode")

    @tts_backend_mode.setter
    def tts_backend_mode(self, value):
        self.set("tts_backend_mode", value)

    @property
    def tts_backend_url(self):
        """Base URL of the remote TTS service (used when tts_backend_mode='remote')."""
        return self.get("tts_backend_url")

    @tts_backend_url.setter
    def tts_backend_url(self, value):
        self.set("tts_backend_url", value)

    @property
    def tts_autostart_service(self):
        """Whether to auto-start the TTS service subprocess on launch."""
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
