"""
Phase 02 — Text Normalization Debug Writer

Copilot Instructions:
- Follow Phase 00 and Phase 01 debug.py EXACTLY.
- Write ONLY:
    normalized.json
    stats.json
    meta.json
    summary.json
"""

import json
from pathlib import Path

def write_debug_artifacts(context: dict, output_model):
    base = Path(context["artifact_root"]) / "phases" / "02_cleaning"
    base.mkdir(parents=True, exist_ok=True)

    # Write normalized chapters JSON (required)
    (base / "normalized.json").write_text(
        json.dumps(output_model.normalized_chapters, indent=2),
        encoding="utf-8"
    )

    # NEW: Write per-chapter debug files
    debug_dir = base / "chapters_debug"
    debug_dir.mkdir(exist_ok=True)

    for chapter_id, debug in output_model.debug.items():
        chapter_dir = debug_dir / chapter_id
        chapter_dir.mkdir(exist_ok=True)

        # raw HTML input
        (chapter_dir / "raw_input.html").write_text(
            debug["raw_input"],
            encoding="utf-8"
        )

        # after boilerplate removal
        (chapter_dir / "after_boilerplate.txt").write_text(
            debug["after_boilerplate"],
            encoding="utf-8"
        )

        # after HTML stripping
        (chapter_dir / "after_html_stripping.txt").write_text(
            debug["after_html_stripping"],
            encoding="utf-8"
        )

        # final normalized output
        (chapter_dir / "final_normalized.txt").write_text(
            debug["final_normalized"],
            encoding="utf-8"
        )
