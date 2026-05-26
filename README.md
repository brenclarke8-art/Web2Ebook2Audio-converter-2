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
- **Kokoro-ONNX CLI**: Required for text-to-speech synthesis (see installation instructions)
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

### 4. Install Kokoro-ONNX CLI

The application uses Kokoro-ONNX CLI for multi-speaker text-to-speech synthesis.

**Download or build the CLI:**

1. Visit the Kokoro-ONNX repository: https://github.com/thewh1teagle/kokoro-onnx
2. Download the pre-built binary for your operating system from the releases page
3. Extract and place the executable in a convenient location (e.g., `/usr/local/bin/kokoro-onnx` on Linux/macOS or `C:\Program Files\kokoro-onnx\kokoro-onnx.exe` on Windows)
4. Make note of the full path to the executable - you'll need to configure it in the application

**Alternatively, build from source:**

```bash
# Clone the kokoro-onnx repository
git clone https://github.com/thewh1teagle/kokoro-onnx.git
cd kokoro-onnx

# Follow the build instructions in their README
# The resulting binary will be your kokoro-onnx CLI executable
```

### 5. Install the Application

```bash
pip install -e .
```

This installs the application in "editable" mode, allowing you to make changes to the source code while still using the installed package.

### 6. Configure Kokoro CLI Path

After installation, you'll need to configure the path to your kokoro-onnx executable:

1. Launch the application
2. Navigate to the **Settings** page
3. Enter the full path to your kokoro-onnx executable in the "Kokoro CLI path" field
4. Click "Save Settings"

Alternatively, the TTS page also has a field to set the CLI path.

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
   - Configure the path to kokoro-onnx CLI executable if not already set
   - Assign Kokoro-ONNX voices to dialogue speakers
   - Configure default voice for narration
   - Adjust speech speed (0.5x - 2.0x)

#### 5. **Generate Audio**
   - The system parses dialogue using pattern matching
   - Multi-speaker TTS generates audio with character voices using Kokoro-ONNX CLI
   - Audio files are saved in `<project>/pipeline_work/audio/`

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

### "Kokoro CLI not configured" Error

Make sure you've configured the path to the kokoro-onnx executable:
1. Navigate to **Settings** page
2. Enter the full path to your kokoro-onnx executable
3. Click "Save Settings"

You can download kokoro-onnx from: https://github.com/thewh1teagle/kokoro-onnx

### Kokoro CLI Executable Not Found

Ensure the kokoro-onnx executable:
- Is downloaded and placed in an accessible location
- Has execute permissions (on Linux/macOS: `chmod +x /path/to/kokoro-onnx`)
- Path is correctly configured in Settings

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

- **Check Kokoro-ONNX CLI configuration**: Ensure you're using the latest version
- **Process chapters individually**: Instead of running full pipeline at once
- **Hardware limitations**: Audio generation speed depends on your CPU performance

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
- **TTSEngine**: Kokoro-ONNX CLI integration with multi-speaker support
- **EPUBBuilder**: EPUB3 generation with Media Overlays

Each project maintains its own directory with intermediate files and state preservation for resume support.