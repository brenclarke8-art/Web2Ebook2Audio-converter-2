from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase00FetchOutput(BaseModel):
    source: Dict[str, Any] = Field(..., description="Source object for Phase 01")
    meta: Dict[str, Any] = Field(..., description="Phase metadata")
    input_summary: Dict[str, Any] = Field(..., description="Summary of input fields")
    output_summary: Dict[str, Any] = Field(..., description="Summary of output fields")
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    timings: Dict[str, float] = Field(default_factory=dict)
