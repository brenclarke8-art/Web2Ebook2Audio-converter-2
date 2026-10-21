"""
Phase 09 — File Writing & Export Processor

Copilot Instructions:
- Follow Phase 00–08 processor.py EXACTLY.
- Rewrite export logic using legacy code ONLY as reference:
    legacy/ebook_app/export/*
    legacy/ebook_app/epub/*
    legacy/ebook_app/audio/*
- Writes MUST be deterministic.
- Writes MUST be limited to:
    context["artifact_root"] / "export"
- Do NOT import legacy code.
- Do NOT perform logging.
- Do NOT perform network calls.
"""

import time
import json
from pathlib import Path
from .input_schema import Phase09Input
from .output_schema import Phase09Output

# Helper stubs Copilot will fill in
def _write_metadata(base: Path, manifest: dict) -> str:
    path = base / "metadata.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return str(path)

def _write_audiobook(base: Path, audiobook_manifest: dict) -> dict:
    audio_dir = base / "audiobook"
    audio_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for chapter in audiobook_manifest["chapters"]:
        fake_path = audio_dir / f"{chapter['chapter_id']}.wav"
        with open(fake_path, "wb") as f:
            f.write(b"FAKE AUDIO DATA")
        written.append(str(fake_path))

    return {"dir": str(audio_dir), "files": written}

def _write_epub(base: Path, epub_manifest: dict) -> dict:
    epub_dir = base / "epub"
    epub_dir.mkdir(parents=True, exist_ok=True)

    fake_path = epub_dir / "book.epub"
    with open(fake_path, "wb") as f:
        f.write(b"FAKE EPUB DATA")

    return {"dir": str(epub_dir), "files": [str(fake_path)]}

def process(input_data: Phase09Input, context: dict) -> Phase09Output:
    start = time.time()

    base = Path(context["artifact_root"]) / "export"
    base.mkdir(parents=True, exist_ok=True)

    audiobook = _write_audiobook(base, input_data.package_manifest["audiobook"])
    epub = _write_epub(base, input_data.package_manifest["epub"])
    metadata_path = _write_metadata(base, input_data.package_manifest)

    export_manifest = {
        "audiobook_dir": audiobook["dir"],
        "epub_dir": epub["dir"],
        "metadata_path": metadata_path,
        "files_written": audiobook["files"] + epub["files"] + [metadata_path],
    }

    export_index = {
        "audiobook": audiobook,
        "epub": epub,
        "metadata": {"path": metadata_path},
    }

    output = Phase09Output(
        export_manifest=export_manifest,
        export_index=export_index,
        meta={
            "phase": "09_export",
            "version": "1.0.0",
            "timestamp": time.time(),
        },
        input_summary={
            "manifest_sections": len(input_data.package_manifest),
        },
        output_summary={
            "file_count": len(export_manifest["files_written"]),
        },
        errors=[],
        warnings=[],
        timings={"total_ms": (time.time() - start) * 1000},
    )

    return output
