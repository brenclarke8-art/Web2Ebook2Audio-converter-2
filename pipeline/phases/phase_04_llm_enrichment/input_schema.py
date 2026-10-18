"""
Phase 04 — Character Registry
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List


class Phase04Input(BaseModel):
    segments: List[Dict[str, Any]] = Field(
        ..., description="Segment objects from Phase 03."
    )

    settings: Dict[str, Any] = Field(
        ..., description="Normalized config from Phase 00."
    )
