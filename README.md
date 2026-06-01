# Web2Ebook2Audio-converter-2

A PySide6 desktop application that converts web novels into EPUB3 audiobooks with multi-speaker TTS and Media Overlays.

## Architecture

### Core Components

- **ProjectManager** (`src/ebook_app/core/project_manager.py`): Centralized state management for the current project/book, coordinating between UI, BookLibrary, and PipelineController.
- **SettingsManager** (`src/ebook_app/core/settings_manager.py`): Persistent application settings storage.
- **BookLibrary** (`src/ebook_app/models/book_library.py`): Multi-book library management with metadata and progress tracking.
- **PipelineController** (`src/ebook_app/pipeline_controller.py`): Orchestrates the end-to-end conversion pipeline.

### Project Structure

```
src/ebook_app/
├── core/               # Core application components
│   ├── project_manager.py
│   └── settings_manager.py
├── models/             # Data models and business logic
│   ├── book_library.py
│   ├── epub_builder.py
│   ├── scraper.py
│   ├── tts_engine_cli.py   # Kokoro-ONNX Python API wrapper
│   ├── voice_catalog.py    # Full 28-voice catalog
│   └── ...
├── services/           # Service layer
│   ├── epub_service.py
│   └── ...
├── ui/                 # User interface
│   ├── main_window.py
│   ├── pages/
│   └── ...
├── pipeline_controller.py
└── main.py            # Application entry point
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

The app runs in remote mode, so you must set up **both** environments:

1. GUI environment (Python 3.10+)
2. TTS service environment (Python 3.14 recommended)

### 1) Clone and enter the repository root

```bash
git clone https://github.com/brenclarke8-art/Web2Ebook2Audio-converter-2.git
cd Web2Ebook2Audio-converter-2
```

Before installing, confirm you are in the repo root (must contain `pyproject.toml` and `tts_service/`).

### Quick setup helpers (recommended)

Use one command to create both virtual environments and install dependencies.

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
uvicorn tts_server:app --host 127.0.0.1 --port 5005
```

### 5) Launch the GUI

In a separate terminal, from the repository root, activate the GUI venv and run:

```bash
ebook-audio-studio
```

If the command is not found:

```bash
python -m ebook_app.main
```

### 6) Download Kokoro ONNX model files

The application uses the [Kokoro-ONNX](https://github.com/thewh1teagle/kokoro-onnx) library **as a Python package** — no separate CLI binary is required.

Model files are downloaded and saved to `<repo>/.ebook_audio_studio/models/` by default.

**Method A — In-app (recommended):**

1. Launch the application: `ebook-audio-studio`
2. Navigate to the **Settings** page
3. Click **"Download Models from GitHub"**
4. Wait for the download to complete — the status indicator turns green when ready

**Method B — Command line:**

```python
from ebook_app.models.tts_engine_cli import download_kokoro_models
download_kokoro_models()  # saves to <repo>/.ebook_audio_studio/models/
```

**Method C — Manual placement:**

Download `kokoro-v1.0.onnx` and `voices-v1.0.bin` from
<https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0> and either:
- Place them in `<repo>/.ebook_audio_studio/models/` (auto-discovered), or
- Set custom paths via **Settings → Model file (.onnx)** and **Settings → Voices file (.bin)**

#### Optional: Browser scraping support (Playwright)

If the target site requires JavaScript rendering, install Playwright in the GUI
environment:

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
4. Click **Check Service** — the indicator should turn green
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
from ebook_app.core.settings_manager import SettingsManager
from ebook_app.pipeline_controller import PipelineController

settings = SettingsManager()
pipeline = PipelineController(settings)

# Run individual steps
pipeline.scrape_index()
pipeline.scrape_chapters()
pipeline.clean_chapters()
pipeline.plan_clean_review()
pipeline.llm_semantic_analysis()
pipeline.normalize_llm_output()
pipeline.smart_review_dialogue()
pipeline.tts_generate()
pipeline.epub_build()

# Or run all steps at once
pipeline.run_all()
```

### Project Directory Structure

```
output/
└── <project-name>/
    ├── project.json              # Project metadata and state
    ├── pipeline_work/            # Intermediate files
    │   ├── chapters.json         # Scraped chapter data
    │   ├── translated.json       # Translated content (if applicable)
    │   ├── dialogue.json         # Parsed dialogue segments
    │   ├── audio/                # Generated audio files
    │   │   ├── chapter_001.wav
    │   │   └── ...
    │   ├── audio_timing.json     # Paragraph-to-audio timing map
    │   ├── chapter_info_all.json # Aggregated semantic analysis output
    │   ├── character_database.json
    │   └── semantic_review_plan.json
    └── <project-name>.epub       # Final EPUB3 output
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

Custom paths can be set in **Settings → Kokoro ONNX Models**.

### Configurable Settings

| Setting | Description | Default |
|---|---|---|
| **Output Directory** | Where projects are created | `<repo>/output` |
| **TTS Voice** | Default voice for narration | `af_heart` |
| **Speech Speed** | Global speed multiplier | `1.0` |
| **Model file (.onnx)** | Path to Kokoro ONNX model | auto (see above) |
| **Voices file (.bin)** | Path to Kokoro voices file | auto (see above) |
| **Dialogue LLM URL** | Ollama chat endpoint used for dialogue segmentation | `http://127.0.0.1:11434/api/chat` |
| **Dialogue LLM model** | Ollama model for chapter segmentation | `mistral:instruct` |
| **Dialogue LLM mode** | Segmentation mode (`full` or `off`) | `full` |
| **Dialogue LLM timeout / retries** | Network timeout and retry count for LLM requests | `120s / 1` |

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

**Fix:** Go to **Settings** and click **"Download Models from GitHub"**, or manually place the files in `<repo>/.ebook_audio_studio/models/`.

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

- **ProjectManager**: Centralized state management for the current project
- **SettingsManager**: Persistent application settings (`<repo>/.ebook_audio_studio/settings.json`)
- **BookLibrary**: Multi-book library management
- **PipelineController**: Orchestrates the end-to-end conversion pipeline
- **TTSEngine**: Wraps `kokoro_onnx.Kokoro` with lazy model loading and multi-speaker support
- **EPUBBuilder**: EPUB3 generation with Media Overlays

Each project maintains its own directory with intermediate files and state preservation for resume support.
