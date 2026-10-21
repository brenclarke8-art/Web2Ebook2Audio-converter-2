"""
Phase 08 — Final Packaging

Copilot Instructions:
- Follow Phase 00–07 input_schema.py EXACTLY.
- Do NOT add fields.
- Do NOT import legacy code.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase08Input(BaseModel):
    stitched_audio: List[Dict[str, Any]] = Field(
        ..., description="Stitched audio objects from Phase 07."
    )

    stitched_index: Dict[str, Dict[str, Any]] = Field(
        ..., description="Lookup table from Phase 07."
    )

    settings: Dict[str, Any] = Field(
        ..., description="Normalized config from Phase 00."
    )
