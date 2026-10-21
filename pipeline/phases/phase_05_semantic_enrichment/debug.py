"""
Phase 05 — Semantic Enrichment Debug Writer
"""

import json
from pathlib import Path
from pipeline.phases.debug_utils import to_jsonable
from .output_schema import Phase05Output


def write_debug_artifacts(context: dict, output: Phase05Output):
    base = Path(context["artifact_root"]) / "phases" / "05_semantic_enrichment"
    base.mkdir(parents=True, exist_ok=True)

    with open(base / "enriched_segments.json", "w", encoding="utf-8") as f:
        json.dump(to_jsonable(output.enriched_segments), f, indent=2)

    with open(base / "character_registry.json", "w", encoding="utf-8") as f:
        json.dump(to_jsonable(output.character_registry), f, indent=2)

    with open(base / "enrichment_stats.json", "w", encoding="utf-8") as f:
        json.dump(to_jsonable(output.enrichment_stats), f, indent=2)

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
