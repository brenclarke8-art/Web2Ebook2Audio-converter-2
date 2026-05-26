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

## Installation

```bash
pip install -e .
```

## Usage

```bash
ebook-audio-studio
```

## Development

The application uses a project-based workflow:
1. Create or load a project using ProjectManager
2. Run pipeline steps to convert web content to audiobook
3. Export final EPUB3 with synchronized audio

Each project maintains its own directory under the output folder with intermediate files and state preservation for resume support.