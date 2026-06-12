# ebook_app/text/overrides/override_rules.py
"""Override rule data model and loader."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class OverrideRule:
    pattern: str
    replacement: str
    is_regex: bool = False
    enabled: bool = True
    comment: str = ""


def load_rules(path: str | Path) -> List[OverrideRule]:
    """Load override rules from a JSON file."""
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rules = []
    for item in data:
        rules.append(OverrideRule(
            pattern=item["pattern"],
            replacement=item.get("replacement", ""),
            is_regex=item.get("is_regex", False),
            enabled=item.get("enabled", True),
            comment=item.get("comment", ""),
        ))
    return rules


def save_rules(rules: List[OverrideRule], path: str | Path) -> None:
    """Save override rules to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "pattern": r.pattern,
            "replacement": r.replacement,
            "is_regex": r.is_regex,
            "enabled": r.enabled,
            "comment": r.comment,
        }
        for r in rules
    ]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
