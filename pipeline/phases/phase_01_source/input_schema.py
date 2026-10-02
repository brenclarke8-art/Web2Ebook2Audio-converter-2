"""
Phase 01 — Source Acquisition

Copilot Instructions:
- Follow Phase 00 input_schema.py EXACTLY.
- Do NOT import or reuse legacy code. Use it ONLY as reference:
    legacy/ebook_app/text/*
    legacy/ebook_app/scrape/*
    legacy/ebook_app/parse/*
    legacy/ebook_app/epub/*
    legacy/ebook_app/pdf/*
    legacy/ebook_app/ocr/*
- Do NOT add additional fields.
- This schema defines the boundary for Phase 01.
- All acquisition logic will be implemented in processor.py.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any

class Phase01Input(BaseModel):
    source: Dict[str, Any] = Field(
        ...,
        description="Descriptor for the source content (type, url, file_path, chapter_range)."
    )

    settings: Dict[str, Any] = Field(
        ...,
        description="Normalized config from Phase 00."
    )
