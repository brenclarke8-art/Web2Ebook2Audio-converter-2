# ebook_app/text/overrides/__init__.py
from .override_engine import OverrideEngine
from .override_rules import OverrideRule, load_rules, save_rules
from .glossary_loader import load_glossary, save_glossary

__all__ = [
    "OverrideEngine", "OverrideRule", "load_rules", "save_rules",
    "load_glossary", "save_glossary",
]
