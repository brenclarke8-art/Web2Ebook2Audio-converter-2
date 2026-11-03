# Web2Ebook2Audio Converter 2

Web2Ebook2Audio Converter 2 is a phase-based content pipeline that transforms source material (web, EPUB, PDF, OCR, text) into structured audiobook export artifacts.

## Quick Links

📚 **Documentation:** [`docs/README.md`](docs/README.md)  
🏗️  **Architecture:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)  
📋 **All Phases:** [`docs/PHASES.md`](docs/PHASES.md)  
📑 **Examples:** [`docs/examples/schemas/`](docs/examples/schemas/)

## Pipeline Overview

The pipeline processes content through 11 phases:

```
Input (Web/EPUB/PDF/OCR/Text)
  → Phase 00: Bootstrap & Fetch
  → Phase 01-06: Text Processing & Enrichment
  → Phase 07: TTS Audio Generation
  → Phase 08-10: Assembly & Export
  → Output (MP3/WAV + EPUB)
```

### Phase Summary

| Phase | Name | Responsibility |
|-------|------|-----------------|
| 00 | Bootstrap | Config validation |
| 00 | Fetch | Chapter acquisition |
| 01 | Source | Chapter normalization |
| 02 | Cleaning | Text cleanup |
| 03 | Segmentation | Structure division |
| 04 | Character Registry | Character discovery |
| 05 | Semantic Enrichment | Speaker attribution |
| 06 | Voice Assignment | Voice mapping |
| 07 | TTS | Audio synthesis |
| 08 | Stitching | Audio assembly |
| 09 | Packaging | EPUB + audio bundling |
| 10 | Export | Final output |

See [`docs/PHASES.md`](docs/PHASES.md) for detailed phase descriptions.

## Architecture & Design

- **Deterministic outputs**: Same input → same output every time
- **Pure logic**: Processors have no I/O side effects
- **Typed contracts**: Pydantic schemas for inputs/outputs
- **Isolated phases**: Each phase independent and testable
- **Documented specs**: Every phase has detailed task documentation

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for design decisions and data flow.

## Testing

Run the test suite:

```bash
# All tests
python -m pytest pipeline/tests -q

# Non-live tests (no network/TTS)
python -m pytest -m "not live" pipeline/tests -q

# Specific phase
python -m pytest pipeline/tests/phases/phase_01 -v

# With coverage
python -m pytest pipeline/tests --cov=pipeline
```

## Repository Structure

```
pipeline/               # Active pipeline code
├── phases/             # 11 phase implementations
├── tests/              # Regression test suite
└── README.md           # Pipeline documentation

docs/                   # Consolidated documentation
├── ARCHITECTURE.md     # Design and data flow
├── PHASES.md           # Detailed phase specs
├── examples/           # Example schemas
└── README.md           # Docs index

pytest.ini              # Test configuration
pyproject.toml          # Dependencies
README.md               # This file
```

## Key Conventions

- Every phase has: `input_schema.py`, `output_schema.py`, `processor.py`, `runner.py`, `debug.py`, `tests/`
- **Processor:** Pure business logic (no I/O)
- **Debug:** Filesystem write operations only
- **Runner:** Orchestration and error handling
- **Timestamps:** All set to 0.0 (deterministic)

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for full design details.

## Development

### Add a New Phase

1. Copy structure from existing phase
2. Define input/output schemas
3. Implement processor (pure logic)
4. Write debug artifact writer
5. Add tests with fixtures
6. Update docs

See [`docs/README.md`](docs/README.md) for detailed guides.

## Documentation

Full documentation is in the [`docs/`](docs/) directory:

- **[Architecture Overview](docs/ARCHITECTURE.md)** — How the pipeline works
- **[Phase Specifications](docs/PHASES.md)** — What each phase does
- **[Developer Guide](docs/README.md)** — How to contribute
- **[Example Schemas](docs/examples/schemas/)** — Input/output examples
