from __future__ import annotations

import json

from ebook_app.core import settings_manager as settings_module
from ebook_app.core.settings_manager import SettingsManager


def test_legacy_llm_url_promoted_and_stripped(monkeypatch, tmp_path):
    """dialogue_llm_url is promoted to llm_url and then stripped."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "dialogue_llm_url": "http://legacy.example.com",
                "dialogue_llm_model": "legacy:model",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(settings_module, "APP_HOME_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "DEFAULT_SETTINGS_PATH", settings_path)

    manager = SettingsManager()

    # Legacy values should be promoted to canonical keys
    assert manager.get("llm_url") == "http://legacy.example.com"
    assert manager.get("llm_model") == "legacy:model"

    # Legacy keys must be stripped from data
    assert "dialogue_llm_url" not in manager.data
    assert "dialogue_llm_model" not in manager.data


def test_canonical_keys_take_precedence_over_legacy(monkeypatch, tmp_path):
    """When both llm_url and dialogue_llm_url exist, llm_url wins."""
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

    # Canonical keys preserved as-is
    assert manager.get("llm_model") == "new:model"
    assert manager.get("llm_url") == "http://example.com/v1/chat/completions"

    # Legacy + obsolete keys stripped
    assert "dialogue_llm_semantic_model" not in manager.data
    assert "dialogue_llm_formatter_model" not in manager.data
    assert "dialogue_llm_model" not in manager.data


def test_obsolete_keys_stripped_on_load(monkeypatch, tmp_path):
    """Obsolete keys are automatically removed from data on load."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "dialogue_llm_strict_quotes": True,
                "dialogue_llm_delimited_text_only": False,
                "clean_review_mode": "auto",
                "phase2_batch_size": 5,
                "json_pipeline_enabled": True,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(settings_module, "APP_HOME_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "DEFAULT_SETTINGS_PATH", settings_path)

    manager = SettingsManager()

    for key in (
        "dialogue_llm_strict_quotes",
        "dialogue_llm_delimited_text_only",
        "clean_review_mode",
        "phase2_batch_size",
        "json_pipeline_enabled",
    ):
        assert key not in manager.data, f"Obsolete key '{key}' should have been stripped"


def test_pipeline_mode_default_is_manual(monkeypatch, tmp_path):
    """pipeline_mode defaults to 'manual'."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(settings_module, "APP_HOME_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "DEFAULT_SETTINGS_PATH", settings_path)

    manager = SettingsManager()
    assert manager.get("pipeline_mode") == "manual"


def test_new_keys_present(monkeypatch, tmp_path):
    """New v2 keys are present with correct defaults."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(settings_module, "APP_HOME_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "DEFAULT_SETTINGS_PATH", settings_path)

    manager = SettingsManager()
    assert "pipeline_mode" in manager.data
    assert "translation_enabled" in manager.data
    assert "translation_target_language" in manager.data
    assert "llm_batch_size" in manager.data
    assert "llm_timeout" in manager.data
    assert "llm_retries" in manager.data
