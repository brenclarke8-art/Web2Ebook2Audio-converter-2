"""
Phase 10 — File Writing & Export Processor

Copilot Instructions:
- Follow Phase 00–08 processor.py EXACTLY.
- Rewrite export logic using legacy code ONLY as reference:
    legacy/ebook_app/export/*
    legacy/ebook_app/epub/*
    legacy/ebook_app/audio/*
- Builds MUST be deterministic.
- Do NOT perform filesystem writes (move to debug.py).
- Do NOT import legacy code.
- Do NOT perform logging.
- Do NOT perform network calls.
"""

from .input_schema import Phase10Input
from .output_schema import Phase10Output

def process(input_data: Phase10Input) -> Phase10Output:
    """
    Pure logic: build export manifest and index without filesystem operations.
    All filesystem writes are performed by debug.py.
    """
    
    # Build audiobook manifest from input
    audiobook_manifest = {
        "chapters": input_data.package_manifest.get("audiobook", {}).get("chapters", []),
        "metadata": input_data.package_manifest.get("audiobook", {}).get("metadata", {}),
    }
    
    # Build EPUB manifest from input
    epub_manifest = {
        "content": input_data.package_manifest.get("epub", {}).get("content", []),
        "metadata": input_data.package_manifest.get("epub", {}).get("metadata", {}),
    }
    
    # Build export manifest
    export_manifest = {
        "audiobook": audiobook_manifest,
        "epub": epub_manifest,
        "metadata": input_data.package_manifest.get("metadata", {}),
    }
    
    # Build export index for quick lookup
    export_index = {
        "audiobook": {"chapter_count": len(audiobook_manifest.get("chapters", []))},
        "epub": {"content_count": len(epub_manifest.get("content", []))},
        "metadata": {"keys": list(input_data.package_manifest.get("metadata", {}).keys())},
    }
    
    # Return pure output (no filesystem operations)
    output = Phase10Output(
        export_manifest=export_manifest,
        export_index=export_index,
        meta={
            "phase": "10_export",
            "version": "1.0.0",
            "timestamp": 0.0,
        },
        input_summary={
            "manifest_sections": len(input_data.package_manifest),
        },
        output_summary={
            "export_ready": True,
        },
        errors=[],
        warnings=[],
        timings={"total_ms": 0.0},
    )
    
    return output

