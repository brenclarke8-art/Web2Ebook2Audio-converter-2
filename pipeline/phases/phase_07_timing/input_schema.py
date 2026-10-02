"""
Phase 07 — Audio Stitching

Copilot Instructions:
- Follow Phase 00–06 input_schema.py EXACTLY.
- Do NOT add fields.
- Do NOT import legacy code.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase07Input(BaseModel):
    audio_chunks: List[Dict[str, Any]] = Field(
        ..., description="Audio chunks from Phase 06."
    )

    audio_index: Dict[str, Dict[str, Any]] = Field(
        ..., description="Lookup table from Phase 06."
    )

    settings: Dict[str, Any] = Field(
        ..., description="Normalized config from Phase 00."
    )
