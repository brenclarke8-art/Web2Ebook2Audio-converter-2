"""
Phase 10 — File Writing & Export Debug Writer

Copilot Instructions:
- Follow Phase 00–08 debug.py EXACTLY.
- Write ONLY:
    export_manifest.json
    export_index.json
    meta.json
    summary.json
- Also perform final filesystem export operations.
"""

import json
from pathlib import Path
from .output_schema import Phase10Output

def _write_metadata(base: Path, manifest: dict) -> str:
    """Write manifest to metadata.json file."""
    path = base / "metadata.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return str(path)

def _write_audiobook(base: Path, audiobook_manifest: dict) -> dict:
    """Write audiobook files."""
    audio_dir = base / "audiobook"
    audio_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for chapter in audiobook_manifest.get("chapters", []):
        fake_path = audio_dir / f"{chapter.get('chapter_id', 'unknown')}.wav"
        with open(fake_path, "wb") as f:
            f.write(b"FAKE AUDIO DATA")
        written.append(str(fake_path))

    return {"dir": str(audio_dir), "files": written}

def _write_epub(base: Path, epub_manifest: dict) -> dict:
    """Write EPUB file."""
    epub_dir = base / "epub"
    epub_dir.mkdir(parents=True, exist_ok=True)

    fake_path = epub_dir / "book.epub"
    with open(fake_path, "wb") as f:
        f.write(b"FAKE EPUB DATA")

    return {"dir": str(epub_dir), "files": [str(fake_path)]}

def write_debug_artifacts(context: dict, output: Phase10Output):
    """Write debug artifacts AND perform final export filesystem operations."""
    
    # Write debug metadata artifacts
    debug_base = Path(context["artifact_root"]) / "phases" / "10_export"
    debug_base.mkdir(parents=True, exist_ok=True)

    with open(debug_base / "export_manifest.json", "w", encoding="utf-8") as f:
        json.dump(output.export_manifest, f, indent=2)

    with open(debug_base / "export_index.json", "w", encoding="utf-8") as f:
        json.dump(output.export_index, f, indent=2)

    with open(debug_base / "meta.json", "w", encoding="utf-8") as f:
        json.dump(output.meta, f, indent=2)

    with open(debug_base / "summary.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "input_summary": output.input_summary,
                "output_summary": output.output_summary,
            },
            f,
            indent=2,
        )
    
    # Perform actual export filesystem writes
    export_base = Path(context["artifact_root"]) / "export"
    export_base.mkdir(parents=True, exist_ok=True)
    
    audiobook = _write_audiobook(export_base, output.export_manifest.get("audiobook", {}))
    epub = _write_epub(export_base, output.export_manifest.get("epub", {}))
    metadata_path = _write_metadata(export_base, output.export_manifest.get("metadata", {}))

