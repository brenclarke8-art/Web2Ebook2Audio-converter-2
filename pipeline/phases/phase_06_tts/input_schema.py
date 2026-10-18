"""
Phase 06 — Voice Assignment
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List


class Phase06Input(BaseModel):
    enriched_segments: List[Dict[str, Any]] = Field(
        ..., description="Semantically enriched segments from Phase 05."
    )

    character_registry: List[Dict[str, Any]] = Field(
        ..., description="Canonical character registry from Phase 04/05."
    )

    settings: Dict[str, Any] = Field(
        ..., description="Normalized config from Phase 00."
    )
