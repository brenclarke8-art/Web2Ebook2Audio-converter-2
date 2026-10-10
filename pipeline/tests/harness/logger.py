import json
from pathlib import Path

from .utils import logs_dir


def write_log(log_name, input_artifact, output_artifact):
    base = logs_dir()
    base.mkdir(parents=True, exist_ok=True)

    base_name = str(log_name)[:-5] if str(log_name).endswith(".json") else str(log_name)
    log_path = base / f"{base_name}.json"
    suffix = 1
    while log_path.exists():
        log_path = base / f"{base_name}_{suffix}.json"
        suffix += 1

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
