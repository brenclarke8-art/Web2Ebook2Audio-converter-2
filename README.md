# Web2Ebook2Audio-converter-2

A PySide6 desktop application that converts web novels into EPUB3 audiobooks with multi-speaker TTS and Media Overlays.

## Architecture

### Core Components

- **ProjectManager** (`ebook_app/core/project_manager.py`): Centralized state management for the current project/book, coordinating the library, active project state, and pipeline launches.
- **SettingsManager** (`ebook_app/core/settings_manager.py`): Persistent application settings storage.
- **BookLibrary** (`ebook_app/core/book_library.py`): Multi-book library management with metadata and progress tracking.
- **PipelineWizard** (`ebook_app/gui/pipeline_wizard.py`): The primary GUI workflow for project setup, retrieval, review, audio generation, and output export across phases 1-8 with separate 5a/5b review steps.
- **PipelineController** (`ebook_app/pipeline/controller.py`): Lower-level orchestration API used by the project manager and tests.

### Project Structure

```text
.
├── ebook_app/
│   ├── core/           # Current startup flow, main window, settings, project manager
│   ├── gui/            # Current Qt views, panels, and widgets
│   ├── phases/         # GUI phase controllers
│   ├── pipeline/       # Shared orchestration helpers and controller API
│   ├── text/           # Scraping, parsing, translation, segmentation, speaker ID
│   ├── tts/            # TTS helpers and compatibility exports
│   ├── epub/           # EPUB3 build/output helpers
│   ├── utility/        # Shared runtime/util modules
│   ├── app/            # Legacy compatibility shims and older UI modules
│   └── config/         # Default JSON configuration files
├── tts_service/        # FastAPI Kokoro TTS service and its requirements
├── tests/              # Top-level regression/integration tests
├── scrape_clean/       # Compatibility package for scraping/text cleaning
├── llm_process/        # Compatibility package for LLM/segmentation helpers
├── audio_render/       # Compatibility package for audio/TTS helpers
├── run_app.py          # Root launcher for the desktop app
├── setup_unix.sh       # Unix/macOS environment setup helper
└── setup_windows.ps1   # Windows environment setup helper
```

## Architecture

### Runtime Flow

The desktop app uses a split local setup:

| Component | Description | Python env |
|-----------|-------------|------------|
| GUI app | PySide6 desktop UI, project management, scraping, LLM flow, EPUB export | Python 3.10 |
| TTS service | Local FastAPI service at `tts_service/tts_server.py` used over HTTP | Python 3.14 recommended |

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

The default startup path is `run_app.py` (or the `ebook-audio-studio` console script), which launches the current `ebook_app.core.main` entry point and runs the startup checks before opening the main window.

## System Requirements

- **Python**: 3.10 for the GUI; 3.14 for the TTS service
- **Operating System**: Windows, macOS, or Linux
- **Disk Space**: ~500 MB for model files, plus space for project outputs

## Installation

The app uses separate GUI and TTS environments, so you must set up **both** from the
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

Optional flags to override Python versions:

```powershell
.\setup_windows.ps1 -GuiPython 3.10 -TtsPython 3.14
```

**macOS/Linux:**

```bash
chmod +x ./setup_unix.sh
./setup_unix.sh
```

Optional environment overrides:

```bash
GUI_PYTHON=python3.10 TTS_PYTHON=python3.14 ./setup_unix.sh
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
python run_app.py
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

#### Browser scraping support (Playwright)

Playwright and Chromium are installed automatically by the setup helpers and
are included in the default `requirements.txt`. If you set up the GUI venv
manually, run:

```bash
python -m pip install playwright
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

Or, from the repository root:

```bash
python run_app.py
```

### Application Workflow

The application follows a project-based workflow:

#### 1. **Create/Load a Project**
   - On first launch, use the "New Project" button
   - Projects are stored in the output directory with their own subdirectory
   - Each project maintains `project.json` for resume support

#### 2. **Run the Pipeline**
   - On launch, let the startup checker verify the TTS service, models, and LLM settings
   - Use the **Pipeline** tab to work through the current phase flow:
     Project → Retrieval → Translation → Segmentation → Characters → Classification → Review → Audio → Output
   - Choose a source method (web/EPUB/PDF/file/OCR), verify chapters, then continue phase-by-phase or in the configured automation mode

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

For programmatic use or automation, the lower-level controller still exposes a
condensed 7-step API:

```python
from ebook_app.core.settings_manager import SettingsManager
from ebook_app.pipeline.controller import PipelineController, PipelineSettings
from pathlib import Path

settings = SettingsManager()
ps = PipelineSettings(
    work_dir=Path("output/my-book/pipeline_work"),
    output_dir=Path("output"),
    book_title="My Book",
    book_author="Author Name",
    llm_base_url=settings.get("llm_url", ""),
    llm_model=settings.get("llm_model", ""),
)
controller = PipelineController(ps)

# Step 1 — scrape chapter list from the source
controller.scrape_index()
# Step 2 — retrieve and clean chapter text
controller.scrape_chapters()
# Step 3 — deterministic Pass-1 extraction
controller.pass1_extraction()
# Step 4 — LLM-based Pass-2 classification
controller.pass2_classification()
# Step 5 — rebuild final chapter data after review
controller.smart_review_dialogue()
# Step 6 — TTS audio generation
controller.tts_generate()
# Step 7 — EPUB build with Media Overlays
controller.epub_build()
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
| **TTS service URL** (`tts_backend_url`) | URL for the local HTTP TTS service | `http://127.0.0.1:5005` |
| **Auto-start TTS service** (`tts_autostart_service`) | Start the local TTS service automatically during startup checks | `true` |
| **LLM provider** (`llm_provider`) | LLM backend type used by the classifier UI | `ollama_local` |
| **LLM URL** (`llm_url`) | Chat/completions endpoint used for classification and translation | `http://127.0.0.1:11434/api/chat` |
| **LLM model** (`llm_model`) | Model name used for translation/classification | `qwen2.5-coder:7b` |
| **LLM timeout** (`llm_timeout`) | Network timeout for LLM requests (seconds) | `300` |
| **LLM retries** (`llm_retries`) | Retry count for failed LLM requests | `1` |
| **LLM batch size** (`llm_batch_size`) | Pass-2 request batch size | `20` |
| **LLM chunk size** (`llm_chunk_size`) | Chunk size for dialogue candidate + assignment stages | `6000` |
| **LLM chunk overlap** (`llm_chunk_overlap`) | Overlap between adjacent dialogue chunks | `500` |
| **Translation enabled** (`translation_enabled`) | Turn phase 3 translation on/off | `false` |
| **Translation target language** (`translation_target_language`) | Target language when translation is enabled | `en` |
| **Scraper method** (`scraper_method`) | Retrieval mode used by phase 2 | `browser` |

### Pass-2 JSON Handling Architecture

Pass-2 classification now uses a two-stage JSON flow:

1. **Generation/Extraction stage**: request classification output from the LLM.
2. **Validation/Repair stage**: run strict parsing + schema validation, then:
   - deterministic repair for common format issues (smart quotes, trailing commas, fenced JSON, fragment extraction),
   - model-based repair prompt (JSON-only response) when deterministic repair is not enough,
   - bounded repair retries before marking a segment as `FAILED_FORMAT`.

When `llm_segment_mode=batch`, the classifier automatically switches to single-segment calls for remaining segments if format failures hit `llm_fallback_failure_threshold`.

Dialogue parsing uses two explicit stages per chunk as well:

1. **Dialogue candidate detection** (summary + character context)
2. **Speaker/type assignment** (strict pass-2 candidate protocol)

Pass-2 now validates each candidate object against a strict contract (id/source_id/chunk_id/text/span/delimiter/is_dialogue/type/speaker/character_type/confidence/notes). Invalid schema responses trigger bounded repair retries, then fallback/repair clients, and finally deterministic heuristic fallback for unresolved batches.

Environment overrides are supported:

- `JSON_PIPELINE_ENABLED`
- `JSON_REPAIR_MAX_RETRIES`
- `LLM_SEGMENT_MODE`
- `LLM_FALLBACK_FAILURE_THRESHOLD`

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
python run_app.py
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

Pass-2 LLM logs include structured fields for segment IDs, mode (`batch`/`single`), repair attempts, validation errors, and final status (`OK` or `FAILED_FORMAT`) without dumping full prompts.

### Persistent Malformed LLM JSON

If malformed JSON keeps occurring:

1. Set `llm_segment_mode` to `single` (or `LLM_SEGMENT_MODE=single`) for maximum reliability.
2. Increase `json_repair_max_retries` gradually (default is `2`).
3. Keep `json_pipeline_enabled=true` so deterministic + model repair remains active.
4. Review `pipeline_work/llm_calls.jsonl` and app logs for repeated `FAILED_FORMAT` segments.

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
python -m pytest

# individual suites
python -m pytest tests
python -m pytest scrape_clean/tests
python -m pytest llm_process/tests
python -m pytest audio_render/tests
```

### Code Style

The project uses Python type hints and follows PEP 8 conventions.

### Architecture Overview

- **ProjectManager** (`ebook_app/core/project_manager.py`): Centralized state management for the active project and pipeline runs
- **SettingsManager** (`ebook_app/core/settings_manager.py`): Persistent application settings (`<repo>/.ebook_audio_studio/settings.json`)
- **BookLibrary** (`ebook_app/core/book_library.py`): Multi-book library management
- **PipelineWizard** (`ebook_app/gui/pipeline_wizard.py`): The desktop phase workflow shown in the GUI
- **PipelineController** (`ebook_app/pipeline/controller.py`): Lower-level 7-step orchestration API used by project management and tests
- **TTS helpers** (`ebook_app/tts/` + `tts_service/tts_server.py`): GUI-side client/launch helpers plus the FastAPI Kokoro service
- **EPUBBuilder** (`ebook_app/epub/`): EPUB3 generation with Media Overlays

Each project maintains its own directory with intermediate files and state preservation for resume support.
