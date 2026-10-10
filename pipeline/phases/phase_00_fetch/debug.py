import json
from pathlib import Path

def write_debug_artifacts(context: dict, output_model):
    base = Path(context["artifact_dir"]) / "phase_00_fetch"
    base.mkdir(parents=True, exist_ok=True)

    # Save source.json
    (base / "source.json").write_text(
        json.dumps(output_model.source, indent=2)
    )

    # Save warnings.json
    (base / "warnings.json").write_text(
        json.dumps(output_model.warnings, indent=2)
    )

    # Save errors.json
    (base / "errors.json").write_text(
        json.dumps(output_model.errors, indent=2)
    )

    # Save meta.json
    (base / "meta.json").write_text(
        json.dumps(output_model.meta, indent=2)
    )

    # Save input.json (for reproducibility)
    (base / "input.json").write_text(
        json.dumps(output_model.input_summary, indent=2)
    )

    # Save chapter list
    chapter_list = [c["source"] for c in output_model.source.get("chapters", [])]
    (base / "chapter_list.json").write_text(
        json.dumps(chapter_list, indent=2)
    )

    # Save raw chapter HTML
    raw_dir = base / "chapters_raw"
    raw_dir.mkdir(exist_ok=True)

    for idx, chapter in enumerate(output_model.source.get("chapters", []), start=1):
        html = chapter.get("content", "")
        (raw_dir / f"chapter_{idx:03d}.html").write_text(html)
