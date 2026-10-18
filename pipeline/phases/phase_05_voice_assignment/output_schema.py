"""
Phase 05 — Semantic Enrichment
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List


class Phase05Output(BaseModel):
    enriched_segments: List[Dict[str, Any]] = Field(
        ..., description="Segments with semantic attribution metadata."
    )

    character_registry: List[Dict[str, Any]] = Field(
        ..., description="Pass-through canonical character registry."
    )

    enrichment_stats: Dict[str, Any] = Field(
        ..., description="Semantic enrichment counts and confidence summaries."
    )

    meta: Dict[str, Any] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, Any] = Field(..., description="Input summaries.")
    output_summary: Dict[str, Any] = Field(..., description="Output summaries.")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
