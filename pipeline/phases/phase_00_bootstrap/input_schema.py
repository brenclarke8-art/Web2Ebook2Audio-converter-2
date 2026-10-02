from pydantic import BaseModel, Field
from typing import Dict, Any

class Phase00Input(BaseModel):
    """
    Input schema for Phase 00 — Bootstrap & Config Validation.
    Defines the raw configuration inputs required to initialize the pipeline.
    """

    settings: Dict[str, Any] = Field(
        ..., description="Raw settings.json contents loaded by the orchestrator."
    )

    env: Dict[str, Any] = Field(
        ..., description="Environment variables or CLI overrides passed to the pipeline."
    )
