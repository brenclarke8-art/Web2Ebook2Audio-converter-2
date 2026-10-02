"""
Phase 01 — Source Acquisition

Copilot Instructions:
- Follow Phase 00 output_schema.py EXACTLY.
- Do NOT add or remove fields.
- Do NOT change naming conventions.
- This schema defines the required output structure for Phase 01.
- processor.py MUST produce data that conforms to this schema.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase01Output(BaseModel):
    chapter_index: List[Dict[str, Any]] = Field(
        ..., description="List of chapter descriptors."
    )

    raw_payloads: Dict[str, Any] = Field(
        ..., description="Raw HTML/text snapshots per chapter."
    )

    meta: Dict[str, Any] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, Any] = Field(..., description="Input summaries.")
    output_summary: Dict[str, Any] = Field(..., description="Output summaries.")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
