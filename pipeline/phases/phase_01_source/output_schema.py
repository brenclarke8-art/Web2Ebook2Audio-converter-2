"""
Phase 01 — Output Schema

Copilot Instructions:
- Do NOT modify this schema.
- Do NOT add fields.
- Do NOT remove fields.
- The processor MUST return a Phase01Output instance.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase01Output(BaseModel):
    chapter_index: List[Dict[str, Any]] = Field(
        ..., description="List of chapter descriptors."
    )

    raw_payloads: Dict[str, Any] = Field(
        ..., description="Raw HTML or raw text snapshots per chapter (unprocessed)."
    )

    meta: Dict[str, Any] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, Any] = Field(..., description="Input summaries.")
    output_summary: Dict[str, Any] = Field(..., description="Output summaries.")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
