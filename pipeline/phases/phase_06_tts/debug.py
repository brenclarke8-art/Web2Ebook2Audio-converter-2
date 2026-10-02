"""
Phase 06 — Audio Rendering Debug Writer

Copilot Instructions:
- Follow Phase 00–05 debug.py EXACTLY.
- Write ONLY:
    audio_chunks.json
    audio_index.json
    meta.json
    summary.json
"""

import json
from pathlib import Path
from .output_schema import Phase06Output

def write_debug_artifacts(context: dict, output: Phase06Output):
    base = Path(context["artifact_root"]) / "phases" / "06_audio"
    base.mkdir(parents=True, exist_ok=True)

    with open(base / "audio_chunks.json", "w", encoding="utf-8") as f:
        json.dump(output.audio_chunks, f, indent=2)

    with open(base / "audio_index.json", "w", encoding="utf-8") as f:
        json.dump(output.audio_index, f, indent=2)

    with open(base / "meta.json", "w", encoding="utf-8") as f:
        json.dump(output.meta, f, indent=2)

    with open(base / "summary.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "input_summary": output.input_summary,
                "output_summary": output.output_summary,
            },
            f,
            indent=2,
        )
