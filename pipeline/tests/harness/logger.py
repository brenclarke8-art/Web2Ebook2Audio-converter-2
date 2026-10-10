import json
from pathlib import Path

from .utils import logs_dir

def write_log(log_name, input_artifact, output_artifact):
    """Write a JSON log file and return the created log path."""
    log_directory = logs_dir()
    log_directory.mkdir(parents=True, exist_ok=True)

    log_filename = Path(str(log_name)).name
    if not log_filename.endswith(".json"):
        log_filename = f"{log_filename}.json"

    log_path = log_directory / log_filename
    with open(log_path, "w", encoding="utf-8") as file_handle:
        json.dump(
            {
                "input_artifact": input_artifact,
                "output_artifact": output_artifact,
            },
            file_handle,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    return log_path
