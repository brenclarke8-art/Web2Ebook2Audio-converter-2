from __future__ import annotations

import json

from ebook_app.app.state import settings_manager as settings_module
from ebook_app.app.state.settings_manager import SettingsManager


def test_load_synchronizes_legacy_and_new_dialogue_model_keys(monkeypatch, tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
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

    assert manager.get("dialogue_llm_model") == "semantic:model"
    assert manager.get("dialogue_llm_semantic_model") == "semantic:model"
    assert manager.get("dialogue_llm_formatter_model") == "semantic:model"
