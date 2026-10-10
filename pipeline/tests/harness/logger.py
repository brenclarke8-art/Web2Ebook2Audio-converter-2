import json
from pathlib import Path

from .utils import logs_dir

MAX_LOG_FILE_ATTEMPTS = 1000


def write_log(log_name, input_artifact, output_artifact):
    """Write a JSON log file and return the created log path."""
    log_directory = logs_dir()
    log_directory.mkdir(parents=True, exist_ok=True)

    raw_log_name = Path(str(log_name)).name
    log_base_name = Path(raw_log_name).stem.lstrip(".").strip()
    if not log_base_name:
        log_base_name = "log"
    for suffix in range(MAX_LOG_FILE_ATTEMPTS):
        candidate_name = (
            f"{log_base_name}.json" if suffix == 0 else f"{log_base_name}_{suffix}.json"
        )
        log_path = log_directory / candidate_name
        try:
            with open(log_path, "x", encoding="utf-8") as file_handle:
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
        except FileExistsError:
            continue

    raise RuntimeError(
        f"Unable to create a unique log file for '{log_base_name}' after {MAX_LOG_FILE_ATTEMPTS} attempts."
    )
