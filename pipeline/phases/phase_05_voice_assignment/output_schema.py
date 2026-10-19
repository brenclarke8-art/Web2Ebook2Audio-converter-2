"""
Phase 05 — Semantic Enrichment
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from pipeline.phases.shared_schemas import CharacterEntry


class EnrichedSegment(BaseModel):
    segment_id: str
    primary_type: str
    speaker_id: Optional[str] = None
    thought_owner_id: Optional[str] = None
    pov_character_id: Optional[str] = None
    referenced_characters: List[str] = Field(default_factory=list)
    emotion_tag: Optional[str] = None
    classification_confidence: float
    speaker_confidence: Optional[float] = None


class Phase05Output(BaseModel):
    enriched_segments: List[EnrichedSegment] = Field(
        ..., description="Segments with semantic attribution metadata."
    )

    character_registry: List[CharacterEntry] = Field(
        ..., description="Pass-through canonical character registry."
    )

    enrichment_stats: Dict[str, object] = Field(
        ..., description="Semantic enrichment counts and confidence summaries."
    )

    meta: Dict[str, object] = Field(..., description="Phase metadata.")
    input_summary: Dict[str, object] = Field(..., description="Input summaries.")
    output_summary: Dict[str, object] = Field(..., description="Output summaries.")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
