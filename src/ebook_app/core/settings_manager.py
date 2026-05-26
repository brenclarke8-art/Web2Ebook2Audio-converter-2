# src/ebook_app/core/settings_manager.py
"""Persistent JSON-based settings manager."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


_DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "dark",
    "output_dir": str(Path.home() / "EbookAudioStudio" / "output"),
    "tts_voice": "af_heart",
    "tts_speed": 1.0,
    "kokoro_cli_path": "",
    "translator_provider": "google",
    "translator_target_lang": "en",
    "scraper_delay_ms": 500,
}


class SettingsManager:
    """Load, access, and persist application settings as a JSON file.

    Settings are stored in the user's config directory:
      - Linux/macOS: ~/.config/EbookAudioStudio/settings.json
      - Windows:     %APPDATA%\\EbookAudioStudio\\settings.json

    Usage::

        sm = SettingsManager()
        sm.get("tts_voice")          # returns current value
        sm.set("tts_voice", "am_adam")
        sm.save()
    """

    def __init__(self) -> None:
        self._path = self._resolve_config_path()
        self._data: dict[str, Any] = dict(_DEFAULT_SETTINGS)
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for *key*, falling back to *default*."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Update *key* in memory (call :meth:`save` to persist)."""
        self._data[key] = value

    def all(self) -> dict[str, Any]:
        """Return a shallow copy of all settings."""
        return dict(self._data)

    def save(self) -> None:
        """Write current settings to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._path.exists():
            try:
                with self._path.open("r", encoding="utf-8") as fh:
                    on_disk = json.load(fh)
                # Merge: on-disk values override defaults; new defaults are kept.
                self._data.update(on_disk)
            except (json.JSONDecodeError, OSError):
                # Corrupt or unreadable file — fall back to defaults.
                pass

    @staticmethod
    def _resolve_config_path() -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", Path.home()))
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return base / "EbookAudioStudio" / "settings.json"
