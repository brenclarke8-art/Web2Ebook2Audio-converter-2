"""
Phase 06 — Audio Rendering

Copilot Instructions:
- Follow Phase 00–05 input_schema.py EXACTLY.
- Do NOT add fields.
- Do NOT import legacy code.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase06Input(BaseModel):
    script_segments: List[Dict[str, Any]] = Field(
        ..., description="Script segments from Phase 05."
    )

    script_index: Dict[str, Dict[str, Any]] = Field(
        ..., description="Lookup table from Phase 05."
    )

    settings: Dict[str, Any] = Field(
        ..., description="Normalized config from Phase 00."
    )
