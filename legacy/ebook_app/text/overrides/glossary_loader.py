# ebook_app/text/overrides/glossary_loader.py
"""Glossary loader — reads term-to-replacement mapping from JSON."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict


def load_glossary(path: str | Path) -> Dict[str, str]:
    """Load a glossary from a JSON file (dict of term -> replacement)."""
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items()}
    # Support list-of-pairs format
    if isinstance(data, list):
        return {str(item["term"]): str(item["replacement"]) for item in data}
    return {}


def save_glossary(glossary: Dict[str, str], path: str | Path) -> None:
    """Save a glossary to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(glossary, indent=2, ensure_ascii=False), encoding="utf-8")
