from pydantic import BaseModel, Field
from typing import Dict, Any, List

class Phase00FetchInput(BaseModel):
    index_url: str = Field(..., description="URL of the novel index page")
    chapter_range: List[int] = Field(..., description="[start, end] chapter range")
    settings: Dict[str, Any] = Field(..., description="Pipeline settings")
    env: Dict[str, Any] = Field(..., description="Environment variables")
