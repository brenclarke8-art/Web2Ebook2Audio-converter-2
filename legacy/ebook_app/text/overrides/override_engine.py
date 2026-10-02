# ebook_app/text/overrides/override_engine.py
"""Override engine — applies text substitution rules to translated/scraped text."""
from __future__ import annotations
import logging
import re
from typing import Dict, List

from .override_rules import OverrideRule, load_rules
from .glossary_loader import load_glossary

logger = logging.getLogger(__name__)


class OverrideEngine:
    """
    Apply override rules and glossary substitutions to a block of text.

    Rules are applied in order. Regex rules use re.sub; plain rules use str.replace.
    """

    def __init__(
        self,
        rules: List[OverrideRule] | None = None,
        glossary: Dict[str, str] | None = None,
        case_sensitive: bool = True,
    ):
        self.rules = rules or []
        self.glossary = glossary or {}
        self.case_sensitive = case_sensitive

    @classmethod
    def from_config(cls, rules_path: str, glossary_path: str) -> "OverrideEngine":
        rules = load_rules(rules_path)
        glossary = load_glossary(glossary_path)
        return cls(rules=rules, glossary=glossary)

    def apply(self, text: str) -> str:
        """Apply all rules then the glossary to *text*."""
        for rule in self.rules:
            if not rule.enabled:
                continue
            try:
                if rule.is_regex:
                    flags = 0 if self.case_sensitive else re.IGNORECASE
                    text = re.sub(rule.pattern, rule.replacement, text, flags=flags)
                else:
                    if self.case_sensitive:
                        text = text.replace(rule.pattern, rule.replacement)
                    else:
                        text = re.sub(re.escape(rule.pattern), rule.replacement, text, flags=re.IGNORECASE)
            except re.error as exc:
                logger.warning("Invalid override rule %r: %s", rule.pattern, exc)
        # Apply glossary
        for term, replacement in self.glossary.items():
            text = text.replace(term, replacement)
        return text
