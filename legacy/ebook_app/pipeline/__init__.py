# ebook_app/pipeline/__init__.py
"""Pipeline package.  Imports are lazy to avoid pulling in PySide6 at test time."""
from .phases import PIPELINE_STEPS, PIPELINE_PHASES, PHASE_LABELS

__all__ = [
    "PIPELINE_STEPS",
    "PIPELINE_PHASES",
    "PHASE_LABELS",
]
