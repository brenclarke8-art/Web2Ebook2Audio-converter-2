"""
Phase 10 — File Writing & Export

Copilot Instructions:
- Follow Phase 00–08 input_schema.py EXACTLY.
- Do NOT add fields.
- Do NOT import legacy code.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any

class Phase10Input(BaseModel):
    package_manifest: Dict[str, Any] = Field(
        ..., description="Packaging manifest from Phase 09."
    )

    package_index: Dict[str, Any] = Field(
        ..., description="Lookup table from Phase 09."
    )

    settings: Dict[str, Any] = Field(
        ..., description="Normalized config from Phase 00."
    )
