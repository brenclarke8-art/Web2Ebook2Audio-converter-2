"""
Phase 08 — Final Packaging Debug Writer

Copilot Instructions:
- Follow Phase 00–07 debug.py EXACTLY.
- Write ONLY:
    package_manifest.json
    package_index.json
    meta.json
    summary.json
"""

import json
from pathlib import Path
from .output_schema import Phase08Output

def write_debug_artifacts(context: dict, output: Phase08Output):
    base = Path(context["artifact_root"]) / "phases" / "08_package"
    base.mkdir(parents=True, exist_ok=True)

    with open(base / "package_manifest.json", "w", encoding="utf-8") as f:
        json.dump(output.package_manifest, f, indent=2)

    with open(base / "package_index.json", "w", encoding="utf-8") as f:
        json.dump(output.package_index, f, indent=2)

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
