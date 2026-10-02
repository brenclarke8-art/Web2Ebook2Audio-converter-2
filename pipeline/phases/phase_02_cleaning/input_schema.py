"""
Phase 02 — Text Normalization

Copilot Instructions:
- Follow Phase 00 and Phase 01 input_schema.py EXACTLY.
- Do NOT add fields.
- Do NOT import legacy code.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase02Input(BaseModel):
    chapter_index: List[Dict[str, Any]] = Field(
        ..., description="Chapter descriptors from Phase 01."
    )

    raw_payloads: Dict[str, Any] = Field(
        ..., description="Raw HTML/text payloads from Phase 01."
    )

    settings: Dict[str, Any] = Field(
        ..., description="Normalized config from Phase 00."
    )
