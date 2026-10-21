"""
Phase 05 — Semantic Enrichment
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List


class Phase05Input(BaseModel):
    segments: List[Dict[str, Any]] = Field(
        ..., description="Segment objects from Phase 03."
    )

    character_registry: List[Dict[str, Any]] = Field(
        ..., description="Canonical character registry from Phase 04."
    )

    settings: Dict[str, Any] = Field(
        ..., description="Normalized config from Phase 00."
    )
