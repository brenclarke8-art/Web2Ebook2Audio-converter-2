"""
Phase 06 — Voice Assignment
"""

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class VoiceRegistryEntry(BaseModel):
    voice_id: str
    character_id: Optional[str] = None
    voice_role: str
    provider: str
    voice_name: str
    generation_settings: Dict[str, Any] = Field(default_factory=dict)


class VoiceSegmentAssignment(BaseModel):
    segment_id: str
    voice_id: str
    character_id: Optional[str] = None
    voice_role: str
    primary_type: str


class Phase06Output(BaseModel):
    voice_segments: List[VoiceSegmentAssignment] = Field(
        ..., description="Per-segment voice assignments."
    )

    voice_registry: List[VoiceRegistryEntry] = Field(
        ..., description="Voice-to-character mapping registry."
    )

    meta: Dict[str, Any] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, Any] = Field(..., description="Input summaries.")
    output_summary: Dict[str, Any] = Field(..., description="Output summaries.")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
