#!/usr/bin/env bash
set -euo pipefail

GUI_PYTHON="${GUI_PYTHON:-python3.10}"
TTS_PYTHON="${TTS_PYTHON:-python3.14}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
TTS_REQUIREMENTS="$REPO_ROOT/tts_service/requirements.txt"

if [[ ! -f "$REPO_ROOT/pyproject.toml" || ! -f "$TTS_REQUIREMENTS" ]]; then
  echo "Run this script from the repository root. Missing pyproject.toml or tts_service/requirements.txt." >&2
  exit 1
fi

if ! command -v "$GUI_PYTHON" >/dev/null 2>&1; then
  echo "GUI Python interpreter not found: $GUI_PYTHON" >&2
  exit 1
fi

if ! command -v "$TTS_PYTHON" >/dev/null 2>&1; then
  echo "TTS Python interpreter not found: $TTS_PYTHON" >&2
  exit 1
fi

GUI_VENV="$REPO_ROOT/.venv_gui"
TTS_VENV="$REPO_ROOT/tts_service/.venv_tts"

echo "==> Creating GUI venv with $GUI_PYTHON"
"$GUI_PYTHON" -m venv "$GUI_VENV"
echo "==> Upgrading pip in GUI venv"
"$GUI_VENV/bin/python" -m pip install --upgrade pip
echo "==> Installing GUI dependencies (editable)"
"$GUI_VENV/bin/python" -m pip install -e "$REPO_ROOT"
echo "==> Installing dev dependencies (pytest) in GUI venv"
"$GUI_VENV/bin/python" -m pip install -e "$REPO_ROOT[dev]"
echo "==> Installing Playwright Chromium in GUI venv"
"$GUI_VENV/bin/python" -m playwright install chromium

echo "==> Creating TTS venv with $TTS_PYTHON"
"$TTS_PYTHON" -m venv "$TTS_VENV"
echo "==> Upgrading pip in TTS venv"
"$TTS_VENV/bin/python" -m pip install --upgrade pip
echo "==> Installing TTS service dependencies"
"$TTS_VENV/bin/python" -m pip install -r "$TTS_REQUIREMENTS"

echo
echo "Setup complete."
echo "Start TTS service:"
echo "  cd \"$REPO_ROOT/tts_service\""
echo "  \"$TTS_VENV/bin/python\" -m uvicorn tts_server:app --host 127.0.0.1 --port 5005"
echo
echo "Start GUI:"
echo "  \"$GUI_VENV/bin/python\" -m ebook_app.app.main"
