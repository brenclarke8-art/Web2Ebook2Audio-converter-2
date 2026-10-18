from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

class Phase00FetchInput(BaseModel):
    index_url: str = Field(..., description="URL of the novel index page")
    chapter_range: List[int] = Field(..., description="[start, end] chapter range")
    chapter_example_1: Optional[str] = Field(default=None, description="Known chapter URL example 1")
    chapter_example_2: Optional[str] = Field(default=None, description="Known chapter URL example 2")
    chapter_example_3: Optional[str] = Field(default=None, description="Known chapter URL example 3")
    settings: Dict[str, Any] = Field(..., description="Pipeline settings")
    env: Dict[str, Any] = Field(..., description="Environment variables")
