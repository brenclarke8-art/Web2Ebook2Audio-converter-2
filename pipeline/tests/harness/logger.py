import json
from pathlib import Path

from .utils import logs_dir


def write_log(log_name, input_artifact, output_artifact):
    base = logs_dir()
    base.mkdir(parents=True, exist_ok=True)

    base_name = str(log_name)[:-5] if str(log_name).endswith(".json") else str(log_name)
    suffix = 0
    while True:
        filename = f"{base_name}.json" if suffix == 0 else f"{base_name}_{suffix}.json"
        log_path = base / filename
        try:
            with open(log_path, "x", encoding="utf-8") as f:
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
        except FileExistsError:
            suffix += 1
