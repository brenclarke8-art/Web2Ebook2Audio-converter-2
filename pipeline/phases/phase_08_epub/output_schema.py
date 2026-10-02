"""
Phase 08 — Final Packaging

Copilot Instructions:
- Follow Phase 00–07 output_schema.py EXACTLY.
- Do NOT add or remove fields.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any

class Phase08Output(BaseModel):
    package_manifest: Dict[str, Any] = Field(
        ..., description="Audiobook + EPUB packaging manifest."
    )

    package_index: Dict[str, Any] = Field(
        ..., description="Lookup table for packaging components."
    )

    meta: Dict[str, Any] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, Any] = Field(..., description="Input summaries.")
    output_summary: Dict[str, Any] = Field(..., description="Output summaries.")
    errors: list = Field(default_factory=list)
    warnings: list = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
