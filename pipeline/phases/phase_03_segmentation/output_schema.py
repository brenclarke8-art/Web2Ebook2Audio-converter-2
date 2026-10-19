"""
Phase 03 — Segmentation
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class Segment(BaseModel):
    segment_id: str
    chapter_id: str
    sequence: int
    paragraph_index: int
    structural_type: str
    text: str
    text_markers: List[str] = Field(default_factory=list)
    source_offset_start: Optional[int] = None
    source_offset_end: Optional[int] = None


class Phase03Output(BaseModel):
    segments: List[Segment] = Field(
        ..., description="List of deterministic structural analysis segments."
    )

    segmentation_stats: Dict[str, Dict[str, int] | int] = Field(
        ..., description="Segmentation statistics across chapters and structural types."
    )

    meta: Dict[str, object] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, object] = Field(..., description="Input summaries.")
    output_summary: Dict[str, object] = Field(..., description="Output summaries.")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
