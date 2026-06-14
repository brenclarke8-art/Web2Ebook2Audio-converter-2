# ebook_app/runtime_paths.py
"""Lightweight stdlib-only module that resolves runtime filesystem paths.

Keeping this free of Qt and heavy optional dependencies allows non-GUI
modules (e.g. model-setup helpers, tests) to import these paths without
pulling in PySide6 or audio libraries.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _default_app_home() -> Path:
    """Resolve repository-local runtime home (overridable via env var)."""
    env_home = os.environ.get("EBOOK_AUDIO_STUDIO_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        # New layout: pyproject.toml sits alongside the top-level ebook_app/ package.
        if (parent / "pyproject.toml").exists() and (parent / "ebook_app").is_dir():
            return parent / ".ebook_audio_studio"
    logger.warning(
        "Repository root could not be detected from %s; falling back to current working directory.",
        here,
    )
    return (Path.cwd() / ".ebook_audio_studio").resolve()


APP_HOME_DIR = _default_app_home().resolve()
DEFAULT_SETTINGS_PATH = APP_HOME_DIR / "settings.json"
