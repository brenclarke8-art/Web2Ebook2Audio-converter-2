# Web2Ebook2Audio Converter 2

Web2Ebook2Audio Converter 2 is a phase-based content pipeline that transforms source material (web, EPUB, PDF, OCR, text) into structured audiobook export artifacts.

## Current Pipeline Layout

- `pipeline/phases/phase_00_bootstrap` — config normalization and readiness checks
- `pipeline/phases/phase_00_fetch` — web chapter acquisition (network-enabled)
- `pipeline/phases/phase_01_source` — source-to-chapter/raw payload normalization
- `pipeline/phases/phase_02_cleaning` — deterministic text cleaning and chapter stats
- `pipeline/phases/phase_03_segmentation` — structural segmentation
- `pipeline/phases/phase_04_character_registry` — character discovery and canonical IDs
- `pipeline/phases/phase_05_semantic_enrichment` — narration/dialogue/thought attribution
- `pipeline/phases/phase_06_voice_assignment` — voice mapping
- `pipeline/phases/phase_08_timing` — phase-07 contract (audio stitching)
- `pipeline/phases/phase_09_packaging` — phase-08 contract (packaging)
- `pipeline/phases/phase_10_validation` — currently duplicates phase-09 export contract

## Contracts and Conventions

- Every phase exposes `input_schema.py`, `output_schema.py`, `processor.py`, `runner.py`, `debug.py`, and tests.
- Runner contract is consistent: validate input model -> call `process()` -> write debug artifacts -> return dict.
- `processor.py` owns business logic.
- `debug.py` owns artifact writing.
- Phase 00 fetch persists learned scraping rules when available.

## Testing

- Run all pipeline tests:
  - `python -m pytest -q pipeline/tests`
- Run non-live tests:
  - `python -m pytest -q -m "not live" pipeline/tests`
- Run live tests:
  - `python -m pytest -q -m live pipeline/tests/phases`

## Documentation Added in This Task

- `infoArchitecture/`
- `infoPhases/`
- `infoSchemas/`
- `Research/`
