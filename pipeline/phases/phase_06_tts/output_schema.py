"""
Phase 06 — Voice Assignment
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List


class Phase06Output(BaseModel):
    voice_segments: List[Dict[str, Any]] = Field(
        ..., description="TTS-ready segments with voice IDs."
    )

    voice_registry: List[Dict[str, Any]] = Field(
        ..., description="Voice-to-character mapping registry."
    )

    meta: Dict[str, Any] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, Any] = Field(..., description="Input summaries.")
    output_summary: Dict[str, Any] = Field(..., description="Output summaries.")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
