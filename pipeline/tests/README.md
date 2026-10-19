# Pipeline Test Suite

This directory contains the pipeline-level tests, synthetic fixtures, and regression snapshots.

## How to run tests

- Run all pipeline tests:
  - `python -m pytest -q pipeline/tests`
- Run only non-live tests:
  - `python -m pytest -q -m "not live" pipeline/tests`
- Run live real-site tests:
  - `python -m pytest -q -m live pipeline/tests/phases`

## How to add new phases

1. Add the new phase implementation under `pipeline/phases/phase_NN_<name>/`.
2. Add phase tests under `pipeline/tests/phases/phase_NN/`.
3. Follow existing patterns:
   - synthetic/basic tests
   - structure/contract tests
   - failure-path tests (if applicable)
4. Add/update pipeline chain coverage in `pipeline/tests/phases/pipeline/` if the phase affects end-to-end behavior.
5. Use `pipeline/tests/harness/runner.py::run_phase(...)` so input/output is logged consistently.

## How to add fixtures

- Place fixtures under:
  - `pipeline/tests/fixtures/phase_00/`
  - `pipeline/tests/fixtures/phase_01/`
  - `pipeline/tests/fixtures/phase_02/`
  - shared snapshots: `pipeline/tests/fixtures/shared/`
- Keep fixtures synthetic and deterministic.
- Prefer one fixture per responsibility (index HTML, chapter HTML, source JSON, raw payload JSON, etc).
- Update helpers in phase test folders when fixture-loading logic is shared.

## How logs work

- Harness logs are written by `pipeline/tests/harness/logger.py`.
- `run_phase(...)` writes a JSON log for each phase invocation to:
  - `pipeline/tests/logs/`
- Log schema:
  - `input_artifact`
  - `output_artifact` (or `{ "error": ... }` if phase execution raises)
- Log filenames are unique (`<name>.json`, `<name>_1.json`, ...), so previous runs are preserved.

## How regression snapshots work

- Regression snapshots are stored in:
  - `pipeline/tests/fixtures/shared/regression_phase00.json`
  - `pipeline/tests/fixtures/shared/regression_phase01.json`
  - `pipeline/tests/fixtures/shared/regression_phase02.json`
- Use them as stable expected baselines for shape/content checks.
- When behavior intentionally changes, update snapshots in the same change and keep them aligned with current processor output.

## Phase 03–06 contract checks

- Phase 03 segments are structural-only and ordered by `chapter_id` + `sequence`.
- Phase 04 registry emits canonical `character_id` plus unified `character_profile`.
- Phase 05 semantic output uses a single `primary_type` with confidence metrics.
- Phase 06 voice assignment supports both manual and adaptive mode contracts.
