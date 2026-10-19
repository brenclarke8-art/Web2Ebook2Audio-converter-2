"""
Phase 04 — Character Registry
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List


class Phase04Output(BaseModel):
    character_registry: List[Dict[str, Any]] = Field(
        ..., description="Book-wide canonical character registry."
    )

    segments: List[Dict[str, Any]] = Field(
        ..., description="Pass-through segments from Phase 03."
    )

    meta: Dict[str, Any] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, Any] = Field(..., description="Input summaries.")
    output_summary: Dict[str, Any] = Field(..., description="Output summaries.")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
