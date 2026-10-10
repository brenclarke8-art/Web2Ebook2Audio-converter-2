# Pipeline Test Suite

This directory contains the Phase 00/01/02 and pipeline-level tests, plus synthetic fixtures and regression snapshots.

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

## How to add new real-world sites

1. Add scraper rules in `pipeline/phases/phase_00_fetch/rules/scraper_rules.json`.
2. Add synthetic fixture coverage for the site structure under `pipeline/tests/fixtures/phase_00/`.
3. Add/extend Phase 00 site-specific tests in `pipeline/tests/phases/phase_00/`.
4. Add/extend pipeline-level live test coverage in `pipeline/tests/phases/pipeline/`.
5. For live tests:
   - mark with `@pytest.mark.live`
   - include network-unavailable skip handling
   - keep deterministic assertions focused on stable outputs (counts, summaries, non-empty cleaned text).
