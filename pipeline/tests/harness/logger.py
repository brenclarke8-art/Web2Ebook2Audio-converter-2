import json
from pathlib import Path

from .utils import logs_dir


def write_log(log_name, input_artifact, output_artifact):
    base = logs_dir()
    base.mkdir(parents=True, exist_ok=True)

    filename = log_name if str(log_name).endswith(".json") else f"{log_name}.json"
    log_path = Path(base) / filename

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "input_artifact": input_artifact,
                "output_artifact": output_artifact,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    return log_path
