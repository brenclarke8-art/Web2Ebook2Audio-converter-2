import json
from pathlib import Path

def write_debug_artifacts(context: dict, output_model):
    base = Path(context["artifact_dir"]) / "phase_00_fetch"
    base.mkdir(parents=True, exist_ok=True)

    # Write source.json
    (base / "source.json").write_text(
        json.dumps(output_model.source, indent=2)
    )

    # Write warnings
    (base / "warnings.json").write_text(
        json.dumps(output_model.warnings, indent=2)
    )

    # Write meta
    (base / "meta.json").write_text(
        json.dumps(output_model.meta, indent=2)
    )
