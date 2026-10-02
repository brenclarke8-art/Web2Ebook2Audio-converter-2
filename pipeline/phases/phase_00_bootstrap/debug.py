import json
from pathlib import Path
from .output_schema import Phase00Output

def write_debug_artifacts(context: dict, output: Phase00Output):
    """
    Writes Phase 00 debug artifacts to:
    pipeline/artifacts/phases/00_bootstrap/
    """

    base = Path(context["artifact_root"]) / "phases" / "00_bootstrap"
    base.mkdir(parents=True, exist_ok=True)

    # readiness.json
    with open(base / "readiness.json", "w", encoding="utf-8") as f:
        json.dump(output.readiness_report, f, indent=2)

    # meta.json
    with open(base / "meta.json", "w", encoding="utf-8") as f:
        json.dump(output.meta, f, indent=2)

    # summary.json
    with open(base / "summary.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "input_summary": output.input_summary,
                "output_summary": output.output_summary,
            },
            f,
            indent=2,
        )
