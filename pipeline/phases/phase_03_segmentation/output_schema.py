"""
Phase 03 — Segmentation

Copilot Instructions:
- Follow Phase 00–02 output_schema.py EXACTLY.
- Do NOT add or remove fields.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase03Output(BaseModel):
    segments: List[Dict[str, Any]] = Field(
        ..., description="List of segmented text blocks."
    )

    segment_index: Dict[str, Dict[str, Any]] = Field(
        ..., description="Lookup table for segments."
    )

    meta: Dict[str, Any] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, Any] = Field(..., description="Input summaries.")
    output_summary: Dict[str, Any] = Field(..., description="Output summaries.")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
