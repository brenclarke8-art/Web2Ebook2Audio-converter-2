"""
Phase 05 — Audio Script Generation

Copilot Instructions:
- Follow Phase 00–04 input_schema.py EXACTLY.
- Do NOT add fields.
- Do NOT import legacy code.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase05Input(BaseModel):
    enriched_segments: List[Dict[str, Any]] = Field(
        ..., description="Enriched segment objects from Phase 04."
    )

    enriched_index: Dict[str, Dict[str, Any]] = Field(
        ..., description="Lookup table from Phase 04."
    )

    settings: Dict[str, Any] = Field(
        ..., description="Normalized config from Phase 00."
    )
