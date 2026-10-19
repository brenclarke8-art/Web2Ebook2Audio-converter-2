"""Shared schema models used across multiple pipeline phases."""

from pydantic import BaseModel, Field
from typing import Any, Dict, List


class CharacterEntry(BaseModel):
    character_id: str
    canonical_name: str
    aliases: List[str] = Field(default_factory=list)
    importance: str
    first_seen_segment: str
    character_profile: Dict[str, Any] = Field(default_factory=dict)
