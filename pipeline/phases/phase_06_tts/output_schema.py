"""
Phase 06 — Audio Rendering

Copilot Instructions:
- Follow Phase 00–05 output_schema.py EXACTLY.
- Do NOT add or remove fields.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase06Output(BaseModel):
    audio_chunks: List[Dict[str, Any]] = Field(
        ..., description="Rendered audio chunks."
    )

    audio_index: Dict[str, Dict[str, Any]] = Field(
        ..., description="Lookup table for audio chunks."
    )

    meta: Dict[str, Any] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, Any] = Field(..., description="Input summaries.")
    output_summary: Dict[str, Any] = Field(..., description="Output summaries.")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
