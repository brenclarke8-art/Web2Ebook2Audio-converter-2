"""
Phase 08 — Final Packaging Processor

Copilot Instructions:
- Follow Phase 00–07 processor.py EXACTLY.
- Rewrite packaging logic using legacy code ONLY as reference:
    legacy/ebook_app/package/*
    legacy/ebook_app/epub/*
    legacy/ebook_app/audio/*
- Do NOT import legacy code.
- Do NOT perform filesystem writes.
- Do NOT perform logging.
- Do NOT perform network calls.
- All logic must be PURE and DETERMINISTIC.
"""

import time
from .input_schema import Phase08Input
from .output_schema import Phase08Output

# Helper stubs Copilot will fill in
def _build_audiobook_manifest(stitched_audio: list) -> dict:
    chapters = []
    for item in stitched_audio:
        chapters.append({
            "chapter_id": item["chapter_id"],
            "stitched_id": item["stitched_id"],
            "path": item["path"],
            "metadata": item["metadata"],
        })
    return {"chapters": chapters}

def _build_epub_manifest(settings: dict) -> dict:
    """Copilot: rewrite EPUB packaging logic using legacy code ONLY as reference."""
    return {
        "chapters": [],
        "metadata": {
            "title": settings.get("title", "Untitled"),
            "author": settings.get("author", "Unknown"),
            "language": settings.get("language", "en"),
        }
    }

def process(input_data: Phase08Input) -> Phase08Output:
    start = time.time()

    audiobook = _build_audiobook_manifest(input_data.stitched_audio)
    epub = _build_epub_manifest(input_data.settings)

    package_manifest = {
        "audiobook": audiobook,
        "epub": epub,
    }

    package_index = {
        "audiobook": audiobook,
        "epub": epub,
    }

    output = Phase08Output(
        package_manifest=package_manifest,
        package_index=package_index,
        meta={
            "phase": "08_package",
            "version": "1.0.0",
            "timestamp": time.time(),
        },
        input_summary={
            "stitched_count": len(input_data.stitched_audio),
        },
        output_summary={
            "manifest_sections": len(package_manifest),
        },
        errors=[],
        warnings=[],
        timings={"total_ms": (time.time() - start) * 1000},
    )

    return output
