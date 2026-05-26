from __future__ import annotations
import json
from pathlib import Path
from PySide6.QtCore import QObject, Signal


class SettingsManager(QObject):
    settings_changed = Signal(str)

    DEFAULTS = {
        "tts_voice": "af_heart",
        "tts_speed": 1.0,
        "tts_device": "auto",
        "output_dir": "output",
        "theme": "dark",
        "window_width": 1200,
        "window_height": 800,
    }

    def __init__(self):
        super().__init__()
        self.settings_path = Path.home() / ".ebook_audio_studio_settings.json"
        self._settings = {}
        self.load()

    # ---------------------------------------------------------
    # Load / Save
    # ---------------------------------------------------------

    def load(self):
        if self.settings_path.exists():
            try:
                self._settings = json.loads(self.settings_path.read_text())
            except Exception:
                self._settings = {}
        else:
            self._settings = {}

        # Apply defaults for missing keys
        for key, value in self.DEFAULTS.items():
            self._settings.setdefault(key, value)

    def save(self):
        try:
            self.settings_path.write_text(json.dumps(self._settings, indent=2))
        except Exception as e:
            print("Failed to save settings:", e)

    # ---------------------------------------------------------
    # Get / Set
    # ---------------------------------------------------------

    def get(self, key: str):
        return self._settings.get(key, self.DEFAULTS.get(key))

    def set(self, key: str, value):
        self._settings[key] = value
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
    def tts_device(self):
        return self.get("tts_device")

    @tts_device.setter
    def tts_device(self, value):
        self.set("tts_device", value)

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
