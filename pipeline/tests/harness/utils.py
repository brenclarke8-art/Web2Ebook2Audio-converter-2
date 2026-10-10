from pathlib import Path


def tests_root() -> Path:
    return Path(__file__).resolve().parents[1]


def logs_dir() -> Path:
    return tests_root() / "logs"
