"""
Phase 04 — Semantic Enrichment

Copilot Instructions:
- Follow Phase 00–03 input_schema.py EXACTLY.
- Do NOT add fields.
- Do NOT import legacy code.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase04Input(BaseModel):
    segments: List[Dict[str, Any]] = Field(
        ..., description="Segment objects from Phase 03."
    )

    segment_index: Dict[str, Dict[str, Any]] = Field(
        ..., description="Lookup table from Phase 03."
    )

    settings: Dict[str, Any] = Field(
        ..., description="Normalized config from Phase 00."
    )
