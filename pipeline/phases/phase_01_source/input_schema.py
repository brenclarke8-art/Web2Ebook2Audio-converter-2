"""
Phase 01 — Input Schema

Copilot Instructions:
- Do NOT modify this schema.
- Do NOT add fields.
- Do NOT remove fields.
- This schema defines the ONLY valid input structure for Phase 01.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any

class Phase01Input(BaseModel):
    source: Dict[str, Any] = Field(
        ...,
        description=(
            "Descriptor for the source content. Contains fields such as type, url, "
            "file_path, and optional chapter_range. The exact fields depend on the "
            "source type (web, epub, pdf, text, ocr)."
        )
    )

    settings: Dict[str, Any] = Field(
        ...,
        description="Normalized config from Phase 00."
    )
