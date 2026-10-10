import json
from pathlib import Path

from .utils import logs_dir

MAX_LOG_FILE_ATTEMPTS = 1000


def write_log(log_name, input_artifact, output_artifact):
    """Write a JSON log file and return the created log path."""
    base = logs_dir()
    base.mkdir(parents=True, exist_ok=True)

    log_stem = Path(str(log_name)).name
    base_name = log_stem.removesuffix(".json")
    suffix = 0
    while suffix < MAX_LOG_FILE_ATTEMPTS:
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
                    default=str,
                )
            return log_path
        except FileExistsError:
            suffix += 1

    raise RuntimeError(
        f"Unable to create a unique log file for '{base_name}' after {MAX_LOG_FILE_ATTEMPTS} attempts."
    )
