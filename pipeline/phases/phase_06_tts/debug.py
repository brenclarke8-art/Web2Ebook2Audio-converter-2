"""
Phase 06 — Voice Assignment Debug Writer
"""

import json
from pathlib import Path
from .output_schema import Phase06Output


def write_debug_artifacts(context: dict, output: Phase06Output):
    base = Path(context["artifact_root"]) / "phases" / "06_voice_assignment"
    base.mkdir(parents=True, exist_ok=True)

    with open(base / "voice_segments.json", "w", encoding="utf-8") as f:
        json.dump(output.voice_segments, f, indent=2)

    with open(base / "voice_registry.json", "w", encoding="utf-8") as f:
        json.dump(output.voice_registry, f, indent=2)

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
