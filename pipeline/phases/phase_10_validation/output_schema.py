"""
Phase 09 — File Writing & Export

Copilot Instructions:
- Follow Phase 00–08 output_schema.py EXACTLY.
- Do NOT add or remove fields.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase09Output(BaseModel):
    export_manifest: Dict[str, Any] = Field(
        ..., description="Paths and file list for final export."
    )

    export_index: Dict[str, Any] = Field(
        ..., description="Lookup table for export components."
    )

    meta: Dict[str, Any] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, Any] = Field(..., description="Input summaries.")
    output_summary: Dict[str, Any] = Field(..., description="Output summaries.")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
