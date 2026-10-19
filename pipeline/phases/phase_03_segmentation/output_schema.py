"""
Phase 03 — Segmentation
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List


class Phase03Output(BaseModel):
    segments: List[Dict[str, Any]] = Field(
        ..., description="List of deterministic structural analysis segments."
    )

    segmentation_stats: Dict[str, Any] = Field(
        ..., description="Segmentation statistics across chapters and segment kinds."
    )

    meta: Dict[str, Any] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, Any] = Field(..., description="Input summaries.")
    output_summary: Dict[str, Any] = Field(..., description="Output summaries.")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
