"""
Phase 04 — Semantic Enrichment

Copilot Instructions:
- Follow Phase 00–03 output_schema.py EXACTLY.
- Do NOT add or remove fields.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase04Output(BaseModel):
    enriched_segments: List[Dict[str, Any]] = Field(
        ..., description="Segments with semantic metadata."
    )

    enriched_index: Dict[str, Dict[str, Any]] = Field(
        ..., description="Lookup table for enriched segments."
    )

    meta: Dict[str, Any] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, Any] = Field(..., description="Input summaries.")
    output_summary: Dict[str, Any] = Field(..., description="Output summaries.")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
