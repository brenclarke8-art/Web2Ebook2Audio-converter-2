"""
Phase 03 — Segmentation Debug Writer
"""

import json
from pathlib import Path
from .output_schema import Phase03Output


def write_debug_artifacts(context: dict, output: Phase03Output):
    base = Path(context["artifact_root"]) / "phases" / "03_segmentation"
    base.mkdir(parents=True, exist_ok=True)

    with open(base / "segments.json", "w", encoding="utf-8") as f:
        json.dump(output.segments, f, indent=2)

    with open(base / "segmentation_stats.json", "w", encoding="utf-8") as f:
        json.dump(output.segmentation_stats, f, indent=2)

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
