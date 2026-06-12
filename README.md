# Web2Ebook2Audio-converter-2

A PySide6 desktop application that converts web novels into EPUB3 audiobooks with multi-speaker TTS and Media Overlays.

## Architecture

### Core Components

- **ProjectManager** (`ebook_app/app/state/book_state.py`): Centralized state management for the current project/book, coordinating between UI, BookLibrary, and PipelineController.
- **SettingsManager** (`ebook_app/app/state/settings_manager.py`): Persistent application settings storage.
- **BookLibrary** (`ebook_app/app/state/book_library.py`): Multi-book library management with metadata and progress tracking.
- **PipelineController** (`ebook_app/pipeline/controller.py`): Orchestrates the end-to-end conversion pipeline.

### Project Structure

```
ebook_app/
├── app/                # Application entry point, UI, state management
│   ├── main.py
│   ├── main_window.py
│   ├── ui/             # UI pages
│   ├── state/          # State management (book, chapter, character, settings)
│   ├── widgets/        # Reusable UI widgets
│   └── dialogs/        # Dialog windows
├── pipeline/           # Pipeline controller and phase definitions
│   ├── controller.py
│   └── phases.py
├── text/               # Text processing sub-packages
│   ├── scrape/         # Web/EPUB/PDF/file/OCR importers
│   ├── parse/          # HTML cleaner, text normalizer
│   ├── translate/      # Translation engine and profiles
│   ├── overrides/      # Override rules and glossary
│   ├── segment/        # Dialogue/thought segmentation
│   ├── identify/       # Speaker ID, character DB update
│   └── emotion/        # Emotion tagging
├── tts/                # TTS engine, voice routing, audio utils
├── epub/               # EPUB3 builder (XHTML, SMIL, OPF, TOC)
├── config/             # Default JSON configuration files
├── logs/               # Runtime log outputs
└── output/             # Generated EPUB and audio output
```

## Architecture

### TTS Backend

The application runs in **remote backend mode only**:

| Mode | Description | Python env |
|------|-------------|------------|
| `remote` | Calls `tts_service/tts_server.py` over HTTP | Two envs — GUI (3.10) + TTS service (3.14) |

```
┌──────────────────────────┐
│  GUI (PySide6)           │  ← Python ≥ 3.10, any version PySide6 supports
│  Scraping, EPUB, preview │
└───────────┬──────────────┘
            │ HTTP / JSON
┌───────────▼──────────────┐
│ TTS Service (FastAPI)    │  ← Any Python version (e.g. 3.14)
│ kokoro-onnx + ONNX       │
└──────────────────────────┘
```

This split setup is the supported path: GUI in Python 3.10 and Kokoro service in Python 3.14.

## System Requirements

- **Python**: 3.10 for the GUI; 3.14 for the TTS service
- **Operating System**: Windows, macOS, or Linux
- **Disk Space**: ~500 MB for model files, plus space for project outputs

## Installation

The app runs in remote mode, so you must set up **both** environments from the
repository root:

1. GUI environment (`.venv_gui`, Python 3.10+)
2. TTS service environment (`tts_service/.venv_tts`, Python 3.14 recommended)

### 1) Clone and enter the repository root

```bash
git clone https://github.com/brenclarke8-art/Web2Ebook2Audio-converter-2.git
cd Web2Ebook2Audio-converter-2
```

Before installing, confirm you are in the repo root (must contain `pyproject.toml` and `tts_service/`).

### Quick setup helpers (recommended)

Use one command to create both virtual environments and install dependencies.
These helpers are the easiest way to get a working install because they use the
same venv layout and startup commands documented below.

**Windows (PowerShell):**

```powershell
.\setup_windows.ps1
```

Optional flags:

```powershell
.\setup_windows.ps1 -GuiPython 3.10 -TtsPython 3.14 -InstallBrowser
```

**macOS/Linux:**

```bash
chmod +x ./setup_unix.sh
./setup_unix.sh
```

Optional environment overrides:

```bash
GUI_PYTHON=python3.10 TTS_PYTHON=python3.14 INSTALL_BROWSER=1 ./setup_unix.sh
```

If you prefer manual setup, use the steps below.

### 2) Create and install the GUI environment (required)

**Windows (cmd/PowerShell):**

```powershell
py -3.10 -m venv .venv_gui
.\.venv_gui\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e .
```

**macOS/Linux:**

```bash
python3.10 -m venv .venv_gui
source .venv_gui/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

### 3) Create and install the TTS service environment (required)

**Windows (cmd/PowerShell):**

```powershell
py -3.14 -m venv tts_service\.venv_tts
.\tts_service\.venv_tts\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r .\tts_service\requirements.txt
```

**macOS/Linux:**

```bash
python3.14 -m venv tts_service/.venv_tts
source tts_service/.venv_tts/bin/activate
python -m pip install --upgrade pip
python -m pip install -r tts_service/requirements.txt
```

### 4) Start the TTS service

From the repository root, with the TTS venv active:

```bash
cd tts_service
python -m uvicorn tts_server:app --host 127.0.0.1 --port 5005
```

You can also launch the default local service from **Settings → TTS Backend → Start TTS Server**.

### 5) Launch the GUI

In a separate terminal, from the repository root, activate the GUI venv and run:

```bash
python -m ebook_app.main
```

After the editable install, the console entry point is also available:

```bash
ebook-audio-studio
```

### 6) Download Kokoro ONNX model files

The application uses the [Kokoro-ONNX](https://github.com/thewh1teagle/kokoro-onnx) library **as a Python package** — no separate CLI binary is required.

Model files are downloaded and saved to `<repo>/.ebook_audio_studio/models/` by default.

**Method A — In-app (recommended):**

1. Launch the application: `ebook-audio-studio`
2. Navigate to the **Settings** page
3. Click **"Download + Setup Kokoro Models"**
4. Wait for the download to complete — the status indicator turns green when ready

**Method B — Command line:**

```python
from ebook_app.tts.kokoro_model_setup import download_and_setup_kokoro_models
download_and_setup_kokoro_models()  # saves to <repo>/.ebook_audio_studio/models/
```

**Method C — Manual placement:**

Download `kokoro-v1.0.onnx` and `voices-v1.0.bin` from
<https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0> and either:
- Place them in `<repo>/.ebook_audio_studio/models/` (auto-discovered), or
- Set custom paths via **Settings → TTS Backend → Model file (.onnx)** and **Settings → TTS Backend → Voices file (.bin)**

#### Optional: Browser scraping support (Playwright)

If the target site requires JavaScript rendering, either use the setup helper
with browser support enabled or install Playwright in the GUI environment:

```bash
python -m pip install -e ".[browser]"
python -m playwright install chromium
```

For anti-bot/pop-up bypass flows, enable these in the app UI before scraping:
- Check **Use visible browser (non-headless)**
- Check **Allow manual navigation for protection/popups**
- Set **Manual nav window (sec)** as needed

You can also set custom model paths via environment variables:

```bash
KOKORO_MODEL_PATH=/path/to/kokoro-v1.0.onnx \
KOKORO_VOICES_PATH=/path/to/voices-v1.0.bin \
uvicorn tts_server:app --host 127.0.0.1 --port 5005
```

#### Configure the GUI to use the service

1. Launch `ebook-audio-studio` (from the GUI venv)
2. Navigate to **Settings**
3. Ensure **Service URL** is `http://127.0.0.1:5005`
4. Click **Test TTS Server** — the indicator should turn green
5. Click **Save Settings**

The Pipeline workflow will now use that remote backend for all voice synthesis,
and Settings can be used to verify service health.

---

## Usage

### Starting the Application

```bash
ebook-audio-studio
```

### Application Workflow

The application follows a project-based workflow:

#### 1. **Create/Load a Project**
   - On first launch, use the "New Project" button
   - Projects are stored in the output directory with their own subdirectory
   - Each project maintains `project.json` for resume support

#### 2. **Run the Pipeline**
   - Navigate to the **Pipeline** page
   - Enter the index URL when creating a book project, then load it
   - Use **Check Index** to verify available chapters
   - Run **Run to Character Review** to scrape, translate, and parse chapters

#### 3. **Review Characters and Models**
   - Navigate to **Settings**
   - Check the model status indicator — if amber, download models first
   - Review pending character suggestions and voice assignments before audio generation

#### 4. **Generate Audio + EPUB**
   - Return to the **Pipeline** page
   - Click **Continue Audio + Export**
   - The system generates per-segment audio, builds timing data, and exports the EPUB
   - Audio files are saved in `<project>/pipeline_work/audio/`

#### 5. **Export & Enjoy**
   The final EPUB3 file includes:
   - Original/translated text content
   - Embedded audio files (synchronised per chapter)
   - SMIL Media Overlays for read-aloud support
   - Proper navigation (`nav.xhtml`, `toc.xhtml`) and CSS styling
   - Open in any EPUB3 reader (Thorium Reader, Adobe Digital Editions, etc.)

### Pipeline Steps (Advanced)

For programmatic use or automation:

```python
from ebook_app.app.state.settings_manager import SettingsManager
from ebook_app.pipeline.controller import PipelineController, PipelineSettings
from pathlib import Path

settings = SettingsManager()
ps = PipelineSettings(
    work_dir=Path("output/my-book/pipeline_work"),
    output_dir=Path("output"),
    book_title="My Book",
    book_author="Author Name",
    llm_base_url=settings.get("dialogue_llm_url", ""),
    llm_model=settings.get("dialogue_llm_model", ""),
)
pipeline = PipelineController(ps)

# Phase 1 — scrape chapter list from index URL
pipeline.scrape_index()
# Phase 2 — scrape and clean each chapter's text
pipeline.scrape_chapters()
# Phase 3 — deterministic Pass-1 extraction (no LLM)
pipeline.pass1_extraction()
# Phase 4 — LLM-based Pass-2 classification
pipeline.pass2_classification()
# Phase 5 — rebuild final chapters from reviewed character DB
pipeline.smart_review_dialogue()
# Phase 6 — TTS audio generation (per-segment WAVs + concat)
pipeline.tts_generate()
# Phase 7 — EPUB3 build with Media Overlays
pipeline.epub_build()
```

### Project Directory Structure

```
output/
└── <book-id>/
    ├── project.json              # Project metadata and state
    ├── pipeline_work/            # Intermediate pipeline files
    │   ├── chapters_raw.json     # Scraped chapter list (titles + source URLs)
    │   ├── chXXX_cleaned.txt     # Cleaned chapter text (one file per chapter)
    │   ├── chXXX_pass1.json      # Pass-1 extraction output
    │   ├── chXXX_pass2.json      # Pass-2 LLM classification output
    │   ├── chXXX_final.json      # Final chapter info used for TTS + EPUB
    │   ├── character_database.json
    │   ├── audio/                # Generated audio files
    │   │   ├── chXXX/
    │   │   │   ├── chXXX_seg000.wav  # Per-segment WAV
    │   │   │   └── chXXX.wav         # Concatenated chapter WAV
    │   │   └── …
    │   ├── audio_timing.json     # Paragraph-to-audio timing map
    │   └── epub_build/           # EPUB staging directory
    └── <book-title>.epub         # Final EPUB3 output
```

---

## Configuration

### Settings File Location

Application settings are stored at:

```
<repo>/.ebook_audio_studio/settings.json
```

### Model Files Location

Kokoro ONNX model files are stored at (by default):

```
<repo>/.ebook_audio_studio/models/
├── kokoro-v1.0.onnx
└── voices-v1.0.bin
```

Custom paths can be set in **Settings → TTS Backend → Model file (.onnx)** and **Settings → TTS Backend → Voices file (.bin)**.

### Configurable Settings

| Setting | Description | Default |
|---|---|---|
| **Output Directory** | Where projects are created | `<repo>/output` |
| **Model file (.onnx)** | Path to Kokoro ONNX model (blank = auto-discover) | auto |
| **Voices file (.bin)** | Path to Kokoro voices file (blank = auto-discover) | auto |
| **TTS Voice** | Default voice for narration | `af_heart` |
| **Speech Speed** | Global speed multiplier | `1.0` |
| **Dialogue LLM URL** | Ollama API endpoint for dialogue classification | `http://127.0.0.1:11434/api/generate` |
| **Dialogue LLM model** | Ollama model for Pass-2 chapter classification | `qwen2.5-coder:7b` |
| **Dialogue LLM timeout** | Network timeout for LLM requests (seconds) | `300` |
| **Dialogue LLM retries** | Retry count for failed LLM requests | `1` |

### Available Voices (Kokoro 1.0)

| ID | Gender | Accent |
|---|---|---|
| `af_heart` | Female | American English |
| `af_alloy` | Female | American English |
| `af_aoede` | Female | American English |
| `af_bella` | Female | American English |
| `af_jessica` | Female | American English |
| `af_kore` | Female | American English |
| `af_nicole` | Female | American English |
| `af_nova` | Female | American English |
| `af_river` | Female | American English |
| `af_sarah` | Female | American English |
| `af_sky` | Female | American English |
| `am_adam` | Male | American English |
| `am_echo` | Male | American English |
| `am_eric` | Male | American English |
| `am_fenrir` | Male | American English |
| `am_liam` | Male | American English |
| `am_michael` | Male | American English |
| `am_onyx` | Male | American English |
| `am_puck` | Male | American English |
| `am_santa` | Male | American English |
| `bf_alice` | Female | British English |
| `bf_emma` | Female | British English |
| `bf_isabella` | Female | British English |
| `bf_lily` | Female | British English |
| `bm_daniel` | Male | British English |
| `bm_fable` | Male | British English |
| `bm_george` | Male | British English |
| `bm_lewis` | Male | British English |

---

## Troubleshooting

### Model Files Not Found

The status indicators in Settings show amber (⚠) if model files are missing.

**Fix:** Go to **Settings → TTS Backend** and click **"Download + Setup Kokoro Models"**, or manually place the files in `<repo>/.ebook_audio_studio/models/`.

### TTS Service Dependency Error

This usually means the command was run outside the repository root.

From the repository root, install service dependencies in the TTS venv:

```bash
python -m pip install -r tts_service/requirements.txt
```

Quick check from repo root:

```bash
python -c "from pathlib import Path; print(Path('tts_service/requirements.txt').resolve(), Path('tts_service/requirements.txt').exists())"
```

### Application Won't Start

Try running directly with Python:

```bash
python -m ebook_app.main
```

Check for missing dependencies:

```bash
python -m pip install -e .
```

If `pip install -e .` says no `pyproject.toml` was found, you are not in the repository root.

### Debug Logging

The app now runs with verbose logs by default (`DEBUG`). Override if needed:

```bash
EBOOK_AUDIO_STUDIO_LOG_LEVEL=INFO ebook-audio-studio
```

### Audio Generation is Slow

- CPU inference is expected to be slower than GPU. On a modern CPU, expect ~1× real-time.
- `onnxruntime` will automatically use available hardware acceleration (CUDA on NVIDIA, DirectML on Windows, CoreML on Apple Silicon).
- Process chapters individually rather than running the full pipeline at once.

### EPUB Won't Open in Reader

- Use an EPUB3-compatible reader (Thorium Reader is recommended).
- Some readers don't support Media Overlays (audio synchronisation).
- Validate the EPUB with EPUBCheck: <https://www.w3.org/publishing/epubcheck/>

---

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

The project uses Python type hints and follows PEP 8 conventions.

### Architecture Overview

- **ProjectManager** (`ebook_app/app/state/book_state.py`): Centralized state management for the current project
- **SettingsManager** (`ebook_app/app/state/settings_manager.py`): Persistent application settings (`<repo>/.ebook_audio_studio/settings.json`)
- **BookLibrary** (`ebook_app/app/state/book_library.py`): Multi-book library management
- **PipelineController** (`ebook_app/pipeline/controller.py`): Orchestrates the 7-phase end-to-end conversion pipeline
- **TTSEngine** (`ebook_app/tts/`): Remote TTS via HTTP to `tts_service/tts_server.py`; uses kokoro-onnx
- **EPUBBuilder** (`ebook_app/epub/`): EPUB3 generation with Media Overlays

Each project maintains its own directory with intermediate files and state preservation for resume support.
