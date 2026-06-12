param(
    [string]$GuiPython = "3.10",
    [string]$TtsPython = "3.14",
    [switch]$InstallBrowser
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyproject = Join-Path $repoRoot "pyproject.toml"
$ttsRequirements = Join-Path $repoRoot "tts_service\requirements.txt"

if (-not (Test-Path $pyproject) -or -not (Test-Path $ttsRequirements)) {
    throw "Run this script from the repository root. Missing pyproject.toml or tts_service\requirements.txt."
}

function Run-Step {
    param(
        [string]$Description,
        [scriptblock]$Command
    )
    Write-Host "==> $Description" -ForegroundColor Cyan
    & $Command
}

$guiVenv = Join-Path $repoRoot ".venv_gui"
$ttsVenv = Join-Path $repoRoot "tts_service\.venv_tts"

Run-Step "Creating GUI venv with Python $GuiPython" {
    py -$GuiPython -m venv $guiVenv
}
Run-Step "Upgrading pip in GUI venv" {
    & "$guiVenv\Scripts\python.exe" -m pip install --upgrade pip
}
Run-Step "Installing GUI dependencies (editable)" {
    & "$guiVenv\Scripts\python.exe" -m pip install -e $repoRoot
}

if ($InstallBrowser) {
    Run-Step "Installing browser scraping extras in GUI venv" {
        & "$guiVenv\Scripts\python.exe" -m pip install -e "${repoRoot}[browser]"
    }
    Run-Step "Installing Playwright Chromium in GUI venv" {
        & "$guiVenv\Scripts\python.exe" -m playwright install chromium
    }
}

Run-Step "Creating TTS venv with Python $TtsPython" {
    py -$TtsPython -m venv $ttsVenv
}
Run-Step "Upgrading pip in TTS venv" {
    & "$ttsVenv\Scripts\python.exe" -m pip install --upgrade pip
}
Run-Step "Installing TTS service dependencies" {
    & "$ttsVenv\Scripts\python.exe" -m pip install -r $ttsRequirements
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Start TTS service:"
Write-Host "  cd `"$repoRoot\tts_service`""
Write-Host "  `"$ttsVenv\Scripts\python.exe`" -m uvicorn tts_server:app --host 127.0.0.1 --port 5005"
Write-Host ""
Write-Host "Start GUI:"
Write-Host "  `"$guiVenv\Scripts\python.exe`" -m ebook_app.app.main"
