"""
Phase 02 — Text Normalization

Copilot Instructions:
- Follow Phase 00 and Phase 01 output_schema.py EXACTLY.
- Do NOT add or remove fields.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase02Output(BaseModel):
    normalized_chapters: Dict[str, str] = Field(
        ..., description="Cleaned, normalized chapter text."
    )

    chapter_stats: Dict[str, Dict[str, Any]] = Field(
        ..., description="Stats per chapter (length, word_count, etc)."
    )

    meta: Dict[str, Any] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, Any] = Field(..., description="Input summaries.")
    output_summary: Dict[str, Any] = Field(..., description="Output summaries.")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
