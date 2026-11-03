# Documentation Index

Welcome to the Web2Ebook2Audio Converter 2 documentation!

## Quick Start

- **[Getting Started](../README.md)** — Project overview and setup
- **[Architecture](./ARCHITECTURE.md)** — How the pipeline works
- **[Phases](./PHASES.md)** — What each phase does
- **[Examples](./examples/)** — Example schemas and test data

## Main Documentation

### For Developers

1. **[ARCHITECTURE.md](./ARCHITECTURE.md)**
   - Pipeline design and data flow
   - Phase patterns and contracts
   - Design decisions and rationale
   - Performance considerations

2. **[PHASES.md](./PHASES.md)**
   - Detailed phase descriptions
   - Input/output contracts
   - Data transformations
   - Error handling

3. **[Testing Guide](#testing)** (see below)

### For Contributors

- **Code Style:** Follow existing patterns in `pipeline/phases/`
- **Phase Template:** Copy `pipeline/phases/phase_XX_name/` structure
- **Pull Requests:** Reference this documentation in your PR
- **Tests:** Add tests to `pipeline/phases/phase_XX_name/tests/`

## Reference

### Example Schemas

JSON schema examples for each phase input/output:
- `examples/schemas/Phase*.json`

Copy these to understand the expected format.

### Phase Task Specifications

Each phase has a detailed task document:
- `pipeline/phases/phase_XX_name/tasks.md`

These are the source of truth for phase requirements.

### Test Coverage

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

## Architecture Overview

### Pipeline Phases (11 total)

```
Input Sources (Web/EPUB/PDF/OCR/Text)
    ↓
Phase 00: Bootstrap & Fetch
    ↓
Phase 01-06: Text Processing & Enrichment
    ↓
Phase 07: TTS Audio Generation
    ↓
Phase 08-10: Assembly & Export
    ↓
Output Artifacts (MP3/WAV + EPUB)
```

### Design Principles

1. **Deterministic**: Same input → same output every time
2. **Pure Logic**: Processors have no I/O side effects
3. **Typed Contracts**: Pydantic models for all inputs/outputs
4. **Isolated Phases**: Each phase independent and testable
5. **Documented**: Every phase has detailed task spec

## Key Files

```
pipeline/
├── phases/
│   ├── phase_00_bootstrap/    # Config validation
│   ├── phase_00_fetch/        # Chapter acquisition
│   ├── phase_01_source/       # Source normalization
│   ├── phase_02_cleaning/     # Text cleaning
│   ├── phase_03_segmentation/ # Segment creation
│   ├── phase_04_character_registry/ # Character discovery
│   ├── phase_05_semantic_enrichment/ # Speaker attribution
│   ├── phase_06_voice_assignment/ # Voice mapping
│   ├── phase_07_TTS/          # Audio synthesis (TODO)
│   ├── phase_08_timing/       # Audio stitching
│   ├── phase_09_packaging/    # EPUB + audio bundling
│   ├── phase_10_validation/   # Final export
│   └── tests/                 # Regression tests
├── README.md                  # Pipeline overview
└── debug_utils.py             # Debug helpers

docs/
├── ARCHITECTURE.md            # This directory
├── PHASES.md                  # Phase descriptions
├── examples/
│   └── schemas/              # Example JSON schemas
└── README.md                 # This file
```

## Common Tasks

### Add a New Phase

1. Create `pipeline/phases/phase_XX_name/`
2. Copy structure from existing phase
3. Define `input_schema.py` and `output_schema.py`
4. Implement `processor.py` (pure logic)
5. Implement `debug.py` (artifact writing)
6. Implement `runner.py` (orchestration)
7. Add tests in `tests/`
8. Document in `tasks.md`

### Debug a Phase

1. Check debug artifacts: `<artifact_root>/phases/phase_XX_name/`
2. Review meta.json for error/warning logs
3. Check input_summary.json to understand input
4. Review processor output in output_summary.json
5. Read phase tasks.md for expected behavior

### Run a Single Phase

```python
from pipeline.phases.phase_01_source.runner import run
from pipeline.phases.phase_01_source.input_schema import Phase01Input

input_data = Phase01Input(...)
output = run({"artifact_root": "/tmp/artifacts"}, input_data.dict())
```

### Write a Regression Test

1. Create test case in `tests/test_processor.py`
2. Use `pipeline/tests/harness/runner.py` to execute phase
3. Compare output to snapshot in `tests/fixtures/`
4. Update snapshot when output changes intentionally

## Troubleshooting

### Phase fails with schema error
- Check that output matches declared schema in `output_schema.py`
- Review phase tasks.md for required fields
- Check example schema in `docs/examples/schemas/`

### Determinism issues
- Verify no `time.time()` in processor outputs
- Check for random state or file-system dependency
- Ensure processor is pure logic (no I/O)

### Import errors
- Verify phase directories are in `pipeline/phases/`
- Check that `__init__.py` files exist
- Run `python -m pytest` from repo root

### Tests not running
- Ensure tests are in `phase_XX_name/tests/`
- Run: `python -m pytest pipeline/tests -q`
- Check for missing dependencies: `pip install -e .[dev]`

## Resources

- **Source Code:** `pipeline/phases/*/`
- **Tests:** `pipeline/tests/`
- **Schemas:** `docs/examples/schemas/`
- **Issues:** GitHub issues for the repository
- **Pull Requests:** Reference documentation when submitting PRs

## Contributing

When contributing:

1. Follow the phase pattern (processor/debug/runner)
2. Make outputs deterministic (no timestamps, etc.)
3. Add comprehensive docstrings
4. Write tests for new logic
5. Update docs/PHASES.md with phase description
6. Reference this documentation in your PR

---

**Last Updated:** 2026-11-03  
**Pipeline Version:** 1.0.0
