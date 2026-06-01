from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 5005
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class TTSServiceLaunchSpec:
    program: str
    arguments: tuple[str, ...]
    working_directory: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_tts_service_python(
    *,
    repo_root: Path | None = None,
    current_python: str | None = None,
) -> Path:
    repo_root = (repo_root or _repo_root()).resolve()
    env_python = os.environ.get("EBOOK_AUDIO_STUDIO_TTS_PYTHON", "").strip()
    if env_python:
        candidate = Path(env_python).expanduser().resolve()
        if not candidate.exists():
            raise FileNotFoundError(
                f"EBOOK_AUDIO_STUDIO_TTS_PYTHON does not exist: {candidate}"
            )
        return candidate

    candidates = [
        repo_root / "tts_service" / ".venv_tts" / "Scripts" / "python.exe",
        repo_root / "tts_service" / ".venv_tts" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    fallback = Path(current_python or sys.executable).expanduser().resolve()
    if fallback.exists():
        return fallback
    raise FileNotFoundError("No usable Python interpreter was found for the TTS service.")


def build_tts_service_launch_spec(
    base_url: str,
    *,
    repo_root: Path | None = None,
    current_python: str | None = None,
) -> TTSServiceLaunchSpec:
    repo_root = (repo_root or _repo_root()).resolve()
    service_dir = (repo_root / "tts_service").resolve()
    if not service_dir.exists():
        raise FileNotFoundError(f"TTS service directory not found: {service_dir}")

    parsed = urlparse((base_url or "").strip())
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(
            "Invalid URL format. Expected a full local TTS service URL, such as http://127.0.0.1:5005."
        )
    if parsed.scheme != "http":
        raise ValueError("GUI auto-start only supports local http:// TTS service URLs.")
    if parsed.hostname not in _LOCAL_HOSTS:
        raise ValueError("GUI auto-start only supports local TTS service URLs.")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("GUI auto-start requires a plain host:port TTS service URL.")

    python_executable = resolve_tts_service_python(
        repo_root=repo_root,
        current_python=current_python,
    )
    host = parsed.hostname or _DEFAULT_HOST
    port = parsed.port or _DEFAULT_PORT
    return TTSServiceLaunchSpec(
        program=str(python_executable),
        arguments=(
            "-m",
            "uvicorn",
            "tts_server:app",
            "--host",
            host,
            "--port",
            str(port),
        ),
        working_directory=str(service_dir),
    )


def launch_tts_service(base_url: str) -> int:
    spec = build_tts_service_launch_spec(base_url)
    kwargs = {
        "cwd": spec.working_directory,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    command = [spec.program, *spec.arguments]

    if os.name == "nt":
        # Fall back to 0 so this still works on Python builds where one or both
        # constants are not exposed; in that case the process still launches, but
        # without the extra Windows detachment flags.
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess,
            "CREATE_NEW_PROCESS_GROUP",
            0,
        )
        process = subprocess.Popen(command, creationflags=creationflags, **kwargs)
    else:
        process = subprocess.Popen(command, start_new_session=True, **kwargs)
    pid = process.pid
    if pid is None:
        raise RuntimeError("TTS service process started without a PID.")
    return int(pid)
