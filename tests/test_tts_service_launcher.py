from __future__ import annotations

from pathlib import Path

import pytest

from ebook_app.services.tts_service_launcher import (
    build_tts_service_launch_spec,
    resolve_tts_service_python,
)


def test_resolve_tts_service_python_prefers_tts_service_venv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    venv_python = tmp_path / "tts_service" / ".venv_tts" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")
    monkeypatch.delenv("EBOOK_AUDIO_STUDIO_TTS_PYTHON", raising=False)

    resolved = resolve_tts_service_python(
        repo_root=tmp_path,
        current_python="/usr/bin/current-python",
    )

    assert resolved == venv_python.resolve()


def test_resolve_tts_service_python_falls_back_to_current_interpreter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_python = tmp_path / "python"
    current_python.write_text("", encoding="utf-8")
    monkeypatch.delenv("EBOOK_AUDIO_STUDIO_TTS_PYTHON", raising=False)

    resolved = resolve_tts_service_python(
        repo_root=tmp_path,
        current_python=str(current_python),
    )

    assert resolved == current_python.resolve()


def test_build_launch_spec_parses_host_and_port(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_dir = tmp_path / "tts_service"
    service_dir.mkdir(parents=True)
    venv_python = service_dir / ".venv_tts" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")
    monkeypatch.delenv("EBOOK_AUDIO_STUDIO_TTS_PYTHON", raising=False)

    spec = build_tts_service_launch_spec(
        "http://localhost:5010",
        repo_root=tmp_path,
    )

    assert spec.program == str(venv_python.resolve())
    assert spec.working_directory == str(service_dir.resolve())
    assert spec.arguments[-4:] == ("--host", "localhost", "--port", "5010")


def test_build_tts_service_launch_spec_rejects_remote_url(tmp_path: Path) -> None:
    (tmp_path / "tts_service").mkdir(parents=True)

    with pytest.raises(ValueError, match="local TTS service URLs"):
        build_tts_service_launch_spec("http://10.0.0.8:5005", repo_root=tmp_path)
