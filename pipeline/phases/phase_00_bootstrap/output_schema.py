from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase00Output(BaseModel):
    """
    Output schema for Phase 00 — Bootstrap & Config Validation.
    Produces normalized configuration, readiness checks, and standard artifact metadata.
    """

    normalized_config: Dict[str, Any] = Field(
        ..., description="Canonical runtime configuration derived from raw settings + env."
    )

    readiness_report: Dict[str, Any] = Field(
        ..., description="Environment + dependency readiness checks."
    )

    meta: Dict[str, Any] = Field(
        ..., description="Phase metadata: version, timestamps, hashes, etc."
    )

    input_summary: Dict[str, Any] = Field(
        ..., description="Summaries of input fields for observability."
    )

    output_summary: Dict[str, Any] = Field(
        ..., description="Summaries of output fields for observability."
    )

    errors: List[str] = Field(
        default_factory=list,
        description="List of fatal or non-fatal errors encountered during processing."
    )

    warnings: List[str] = Field(
        default_factory=list,
        description="List of warnings encountered during processing."
    )

    timings: Dict[str, float] = Field(
        default_factory=dict,
        description="Timing information for the phase execution."
    )
