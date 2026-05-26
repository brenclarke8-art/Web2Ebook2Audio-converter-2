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

## System Requirements

- **Python**: 3.10 or higher
- **Operating System**: Windows, macOS, or Linux
- **Optional (for GPU acceleration)**:
  - NVIDIA GPU with CUDA support (Windows/Linux)
  - Apple Silicon with MPS support (macOS)
- **Disk Space**: ~500MB for application + models, plus space for project outputs

## Installation

### 1. Prerequisites

First, ensure you have Python 3.10+ installed:

```bash
python --version  # Should show 3.10 or higher
```

### 2. Clone the Repository

```bash
git clone https://github.com/brenclarke8-art/Web2Ebook2Audio-converter-2.git
cd Web2Ebook2Audio-converter-2
```

### 3. (Optional) Create a Virtual Environment

It's recommended to use a virtual environment to avoid dependency conflicts:

```bash
# On Windows
python -m venv venv
venv\Scripts\activate

# On macOS/Linux
python -m venv venv
source venv/bin/activate
```

### 4. Install PyTorch

The application requires PyTorch for TTS processing. Install the appropriate version for your system:

**For CPU-only (works on all systems):**
```bash
pip install torch torchvision torchaudio
```

**For NVIDIA GPU (CUDA) support:**
```bash
# Visit https://pytorch.org/get-started/locally/ for the latest CUDA version
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**For Apple Silicon (M1/M2/M3) Mac:**
```bash
pip install torch torchvision torchaudio
# MPS acceleration is automatically enabled on compatible devices
```

### 5. Install Kokoro TTS

The application uses Kokoro TTS for multi-speaker text-to-speech synthesis. Install it via:

```bash
pip install kokoro-tts
```

### 6. Install the Application

```bash
pip install -e .
```

This installs the application in "editable" mode, allowing you to make changes to the source code while still using the installed package.

### 7. Verify Installation

```bash
ebook-audio-studio --help
```

If the command is not found, try:
```bash
python -m ebook_app.main
```

## Usage

### Starting the Application

Launch the GUI application:

```bash
ebook-audio-studio
```

### Application Workflow

The application follows a project-based workflow with multiple pipeline steps:

#### 1. **Create/Load a Project**
   - On first launch, use the "New Project" button to create a project
   - Projects are stored in the output directory with their own subdirectory
   - Each project maintains state files (`project.json`) for resume support

#### 2. **Scrape Web Content**
   - Navigate to the **Scraper** page
   - Enter the URL of a web novel table of contents or chapter index
   - Click "Scrape Index" to extract chapter URLs
   - Click "Scrape Chapters" to download chapter content
   - The scraper uses BeautifulSoup for HTML parsing

#### 3. **(Optional) Translate Content**
   - Navigate to the **Translator** page
   - Select source and target languages
   - Uses deep-translator for translation
   - Translation is stored separately from original text

#### 4. **Configure Characters & Voices**
   - Navigate to the **TTS** page
   - Assign Kokoro voices to dialogue speakers
   - Configure default voice for narration
   - Adjust speech speed (0.5x - 2.0x)

#### 5. **Generate Audio**
   - The system parses dialogue using pattern matching
   - Multi-speaker TTS generates audio with character voices
   - Audio files are saved in `<project>/pipeline_work/audio/`
   - Supports GPU acceleration (CUDA/MPS) if available

#### 6. **Create EPUB3 with Media Overlays**
   - Navigate to the **EPUB Export** page
   - The system performs forced alignment to sync text and audio
   - Generates SMIL files for Media Overlays (EPUB3 read-aloud)
   - Creates final EPUB3 file with embedded audio and navigation

#### 7. **Export & Enjoy**
   - The final EPUB3 file includes:
     - Original/translated text content
     - Embedded audio files (synchronized per chapter)
     - SMIL Media Overlays for read-aloud support
     - Proper navigation (nav.xhtml, toc.xhtml)
     - CSS styling
   - Open in compatible EPUB3 readers (Thorium Reader, Adobe Digital Editions, etc.)

### Pipeline Steps (Advanced)

For programmatic use or automation, the pipeline can be controlled via:

```python
from ebook_app.core.settings_manager import SettingsManager
from ebook_app.pipeline_controller import PipelineController

settings = SettingsManager()
pipeline = PipelineController(settings)

# Run individual steps
pipeline.scrape_index()
pipeline.scrape_chapters()
pipeline.translate_chapters()  # Optional
pipeline.parse_dialogue()
pipeline.multispeaker_tts()
pipeline.forced_alignment()
pipeline.smil_generation()
pipeline.epub_export()

# Or run all steps at once
pipeline.run_all()
```

### Project Directory Structure

Each project creates the following structure:

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
    │   ├── alignment/            # Forced alignment data
    │   └── smil/                 # SMIL Media Overlay files
    └── <project-name>.epub       # Final EPUB3 output
```

## Configuration

### Settings Location

Application settings are stored in platform-specific locations:

- **Windows**: `%APPDATA%/EbookAudioStudio/settings.json`
- **macOS**: `~/Library/Application Support/EbookAudioStudio/settings.json`
- **Linux**: `~/.config/EbookAudioStudio/settings.json`

### Configurable Settings

- **Output Directory**: Where projects are created and stored
- **Default Language**: For translation and TTS
- **TTS Voice**: Default voice for narration
- **Speech Speed**: Global speed multiplier
- **Device**: CPU, CUDA, or MPS for TTS inference

## Troubleshooting

### "Kokoro TTS not available" Error

Make sure Kokoro TTS is installed:
```bash
pip install kokoro-tts
```

### "CUDA requested but not available" Error

Either install CUDA-enabled PyTorch or switch to CPU mode in settings:
```bash
# Install CUDA PyTorch
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### Application Won't Start

Try running directly with Python:
```bash
python -m ebook_app.main
```

Check for missing dependencies:
```bash
pip install -r requirements.txt
```

### Audio Generation is Slow

- **Enable GPU acceleration**: Install CUDA (NVIDIA) or use MPS (Apple Silicon)
- **Reduce speech quality**: Lower sample rate in TTS settings (not yet exposed in UI)
- **Process chapters individually**: Instead of running full pipeline at once

### EPUB Won't Open in Reader

- Ensure you're using an EPUB3-compatible reader (Thorium Reader recommended)
- Some readers don't support Media Overlays (audio synchronization)
- Try validating the EPUB with EPUBCheck: https://www.w3.org/publishing/epubcheck/

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

The project uses Python type hints and follows PEP 8 conventions.

### Architecture Overview

- **ProjectManager**: Centralized state management for current project
- **SettingsManager**: Persistent application settings
- **BookLibrary**: Multi-book library management
- **PipelineController**: Orchestrates end-to-end conversion pipeline
- **TTSEngine**: Kokoro TTS integration with multi-speaker support
- **EPUBBuilder**: EPUB3 generation with Media Overlays

Each project maintains its own directory with intermediate files and state preservation for resume support.