"""
Phase 03 — Segmentation

Copilot Instructions:
- Follow Phase 00–02 input_schema.py EXACTLY.
- Do NOT add fields.
- Do NOT import legacy code.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any

class Phase03Input(BaseModel):
    normalized_chapters: Dict[str, str] = Field(
        ..., description="Cleaned chapter text from Phase 02."
    )

    chapter_stats: Dict[str, Any] = Field(
        ..., description="Stats from Phase 02."
    )

    settings: Dict[str, Any] = Field(
        ..., description="Normalized config from Phase 00."
    )
