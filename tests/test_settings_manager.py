from __future__ import annotations

import json

from ebook_app.app.state import settings_manager as settings_module
from ebook_app.app.state.settings_manager import SettingsManager


def test_load_synchronizes_legacy_and_new_llm_keys(monkeypatch, tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "llm_url": "http://example.com/v1/chat/completions",
                "llm_model": "new:model",
                "dialogue_llm_model": "legacy:model",
                "dialogue_llm_semantic_model": "semantic:model",
                "dialogue_llm_formatter_model": "formatter:model",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(settings_module, "APP_HOME_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "DEFAULT_SETTINGS_PATH", settings_path)

    manager = SettingsManager()

    assert manager.get("llm_model") == "new:model"
    assert manager.get("dialogue_llm_model") == "new:model"
    assert manager.get("llm_url") == "http://example.com/v1/chat/completions"
    assert manager.get("dialogue_llm_url") == "http://example.com/v1/chat/completions"
    assert "dialogue_llm_semantic_model" not in manager.data
    assert "dialogue_llm_formatter_model" not in manager.data


def test_load_synchronizes_delimited_text_setting_from_legacy_key(monkeypatch, tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "dialogue_llm_strict_quotes": True,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(settings_module, "APP_HOME_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "DEFAULT_SETTINGS_PATH", settings_path)

    manager = SettingsManager()

    assert manager.get("dialogue_llm_delimited_text_only") is True
    assert manager.get("dialogue_llm_strict_quotes") is True
