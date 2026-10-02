"""
Phase 05 — Audio Script Generation

Copilot Instructions:
- Follow Phase 00–04 output_schema.py EXACTLY.
- Do NOT add or remove fields.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase05Output(BaseModel):
    script_segments: List[Dict[str, Any]] = Field(
        ..., description="Segments formatted for TTS narration."
    )

    script_index: Dict[str, Dict[str, Any]] = Field(
        ..., description="Lookup table for script segments."
    )

    meta: Dict[str, Any] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, Any] = Field(..., description="Input summaries.")
    output_summary: Dict[str, Any] = Field(..., description="Output summaries.")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
