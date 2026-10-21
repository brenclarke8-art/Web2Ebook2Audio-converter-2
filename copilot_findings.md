# Web2Ebook2Audio Architecture Audit

## Executive Summary

Overall status:
- Needs Refactor

The pipeline architecture is directionally correct and mostly aligned with the documented phase boundaries for Phases 01–06, but the repository is not freeze-ready because several phase contracts, debug artifacts, tests, and legacy references still drift from the canonical architecture.

Key findings:
- Phase 00 still emits legacy field names (`content`, `source`) instead of the canonical `raw_content` / `source_url` contract described by the architecture guidance.
- Phase 01 is largely consistent with the intended `chapter_index` + `raw_payloads` boundary and is the strongest phase in the current pipeline.
- Phases 02–06 are structurally close to the documented contracts, but the test suite contains stale imports, duplicate module names, and false assumptions that keep the repository from being cleanly validated.
- The debug artifact set is partially inconsistent with the expected phase outputs and naming conventions, especially around Phase 00 and the phase-specific JSON outputs.
- Freeze readiness is not met because the repository still contains stale legacy references, mismatched module names, and unresolved contract drift.

---

## Phase 00 Findings

### Passed
- The phase is isolated to fetch/network concerns and does not perform semantic enrichment or segmentation in the active processor.
- It correctly fetches the index URL, discovers chapter URLs, applies range selection, and collects per-chapter HTML content in the live processor flow (`pipeline/phases/phase_00_fetch/processor.py`).
- The phase uses a deterministic fetch-and-parse flow and is the only phase expected to make outbound network calls.

### Issues
- The Phase 00 source object is still shaped with legacy keys: `"content"` and `"source"` are used in the chapter records, not the canonical `raw_content` and `source_url` contract described in the architecture brief (`pipeline/phases/phase_00_fetch/processor.py:117-123`).
- This violates the documented source-object contract and means the actual implementation still leaks legacy naming from earlier phases.
- The debug writer emits extra files (`errors.json`, `input.json`, `chapter_list.json`, `chapters_raw/...`) beyond the expected minimal artifacts and creates the wrong shape in some cases (`pipeline/phases/phase_00_fetch/debug.py`).
- The repository still contains legacy content-oriented naming in documentation and logs, which suggests partial migration drift rather than a clean canonical contract.

### Recommended Fixes
- Rename chapter payload fields from `content` to `raw_content` and from `source` to `source_url` in the Phase 00 fetch output and debug artifacts.
- Remove all non-canonical debug outputs that are not part of the expected contract.
- Reconcile the phase 00 task docs and runtime processor so they share the same schema contract.

### Freeze Status
- Not ready for freeze.

---

## Phase 01 Findings

### Passed
- Phase 01 is the best-aligned phase in the current codebase.
- It produces the expected canonical output shape: `chapter_index` and `raw_payloads` (`pipeline/phases/phase_01_source/output_schema.py`).
- The processing logic is explicitly constrained to source extraction only and avoids cleaning, normalization, segmentation, and semantic enrichment (`pipeline/phases/phase_01_source/processor.py`).
- The output contract is explicit and matches the architecture intent.

### Issues
- The implementation does not fully enforce the strict canonical contract in all metadata fields: the chapter entries include extra keys such as `source_type` and `source`, but this is still a structural normalization choice rather than a phase-boundary violation.
- The source object input contract is valid, but the code path still accepts legacy object patterns (`content`, `html`, `text`, `body`) and can produce inconsistent chapter payload normalization depending on the input shape.
- The published task documentation is stronger than the actual test coverage; there is no robust full-source validation suite confirming all source types (`web`, `epub`, `pdf`, `ocr`, `text`) are all canonicalized the same way.

### Recommended Fixes
- Keep the `chapter_index` and `raw_payloads` contract but standardize chapter item keys to the canonical shape in all source loaders.
- Add narrower contract tests for each source type so the Phase 01 boundary remains locked.
- Ensure phase 01 metadata is deterministic and not timestamp-based in the processor output.

### Freeze Status
- Ready with minor fixes.

---

## Phase 02 Findings

### Passed
- The processor performs text normalization responsibilities directly: HTML stripping, whitespace cleanup, paragraph normalization, and per-chapter stats generation (`pipeline/phases/phase_02_cleaning/processor.py`).
- The output schema matches the documented contract: `normalized_chapters` and `chapter_stats` (`pipeline/phases/phase_02_cleaning/output_schema.py`).
- The removal of HTML noise and normalization behavior is consistent with the phase purpose.

### Issues
- The Phase 02 tests are not structurally valid in the current repo: they import `pipeline.phases.phase_02_normalize`, which does not exist (`pipeline/phases/phase_02_cleaning/tests/test_contracts.py`, `test_processor.py`, `test_runner.py`).
- This is a direct sign of stale naming and broken test expectations in the repo.
- The processor uses a chapter stats field `word_count` internally, which is not itself a violation of the phase contract, but it is a legacy-style derived stat and should be kept strictly under the phase’s documented output contract to avoid drift.
- The code includes a `word_count` metric in the stats payload, which is a legacy artifact and a source of confusion if the architecture expects a leaner stats contract.

### Recommended Fixes
- Rename or restore the stale test import paths to the correct module names under `phase_02_cleaning`.
- Review all `chapter_stats` fields for alignment with the final canonical contract and keep only the required metrics.
- Consolidate test fixtures and helpers to avoid stale names.

### Freeze Status
- Needs refactor.

---

## Phase 03 Findings

### Passed
- Phase 03 matches the structural-segmentation boundary: it emits `segment_id`, `chapter_id`, `sequence`, `paragraph_index`, `structural_type`, `text`, `text_markers`, `source_offset_start`, and `source_offset_end` only (`pipeline/phases/phase_03_segmentation/output_schema.py`).
- The processor does not perform character extraction, speaker attribution, or semantic enrichment; it is purely structural (`pipeline/phases/phase_03_segmentation/processor.py`).
- The task documentation explicitly forbids `global_sequence`, `word_count`, and `char_count`, and the implementation does not emit those fields.

### Issues
- The repo does contain stale naming and legacy field references in logs and docs, but the active phase implementation is clean.
- The test suite for this phase is not present under the expected `pipeline/tests/phases/phase_03/...` shape and is effectively underrepresented, which weakens regression coverage.

### Recommended Fixes
- Add or restore the missing phase 03 contract and runner tests to lock the segmentation contract.
- Keep the flow strictly structural and resist any future semantic logic being folded into segmentation.

### Freeze Status
- Ready with minor fixes.

---

## Phase 04 Findings

### Passed
- Phase 04 matches the canonical character-registry output: `character_id`, `canonical_name`, `aliases`, `importance`, `first_seen_segment`, and `character_profile` (`pipeline/phases/shared_schemas.py`).
- The processor does not assign voices or perform speaker attribution; it discovers characters and canonicalizes them (`pipeline/phases/phase_04_character_registry/processor.py`).
- The contract explicitly rejects legacy fields like `gender`, `voice_profile`, `character_traits`, and `entity_type`.

### Issues
- The test suite is thin and does not cover enough edge cases for character canonicalization, alias collisions, or empty-books behavior.
- The registry generation is deterministic but heuristic-heavy, and it may over-identify names from prose without a stronger validation pass.
- The phase maintains a pass-through `segments` list, which is acceptable, but there is no dedicated contract test covering canonical ID propagation downstream.

### Recommended Fixes
- Add contract tests covering empty registry, duplicate aliases, and multiple names in the same paragraph.
- Add stronger canonicalization validation to ensure downstream phases receive consistent `character_id` values.

### Freeze Status
- Ready with minor fixes.

---

## Phase 05 Findings

### Passed
- Phase 05 follows the documented `primary_type` model and returns `speaker_id`, `thought_owner_id`, `pov_character_id`, `referenced_characters`, `emotion_tag`, `classification_confidence`, and `speaker_confidence` (`pipeline/phases/phase_05_semantic_enrichment/output_schema.py`).
- The implementation does not perform voice assignment or TTS preparation.
- It uses canonical `character_id` values throughout the enrichment logic and does not leak raw names into downstream semantics (`pipeline/phases/phase_05_semantic_enrichment/processor.py`).

### Issues
- The current implementation is a lightweight heuristic classifier and is not yet a full semantic understanding layer.
- The test suite is underdeveloped and does not cover the boundary cases for mixed dialogue/narration, missing character registry matches, or confidence edge cases.
- Because module names repeat across phase tests, validation is noisy and may mask real contract failures.

### Recommended Fixes
- Add regression tests for narration/dialogue/thought classification and confidence trimming.
- Expand coverage for missing or ambiguous speaker references.
- Keep the single `primary_type` contract and avoid mixing `content_types` or raw names back into downstream outputs.

### Freeze Status
- Ready with minor fixes.

---

## Phase 06 Findings

### Passed
- The phase is aligned with the voice-mapping boundary and emits `voice_registry` and `voice_segments` as expected (`pipeline/phases/phase_06_voice_assignment/output_schema.py`).
- It supports both `settings.tts.voice_mode == "manual"` and `"adaptive"` (`pipeline/phases/phase_06_voice_assignment/processor.py`).
- It uses canonical `character_id` values when mapping segments to voice entries and does not discover characters or perform semantic analysis.

### Issues
- The current implementation is a functional voice-assignment stub; it does not yet have the robust provider routing or policy logic described in the architecture roadmap.
- There are no dedicated negative-path tests for invalid `voice_mode`, missing provider config, or malformed character registry entries.
- The phase sits near the end of the architecture, but the overall test suite still has import and collection drift that obscures the real phase status.

### Recommended Fixes
- Add tests for invalid `voice_mode`, missing custom voices, and fallback logic.
- Validate registry output against the canonical contract in both `manual` and `adaptive` modes.
- Document the provider and settings contract more explicitly.

### Freeze Status
- Ready with minor fixes.

---

## Cross-Phase Findings

### Schema Drift
- The repository has a documented canonical phase architecture, but several older field names still survive in logs, debug output, and stale examples.
- The biggest schema drift is in Phase 00, which still uses legacy chapter records with `content` and `source` instead of `raw_content` and `source_url`.
- Phase 01 and later phases are much cleaner, but they still risk drifting if legacy field names reappear in generated fixtures or downstream code.

### Deprecated Fields
The active phase contracts have mostly removed the deprecated fields named in the audit brief, but stale references remain in logs and historical artifacts:
- `word_count`
- `char_count`
- `global_sequence`
- `gender`
- `entity_type`
- `voice_profile`
- `character_traits`
- `content_types`
- `speaker_name`
- `character_name`

This is a serious code hygiene issue because the repo still contains evidence of legacy naming in docs, logs, and fixtures even though the active phase contracts aim to remove them.

### Documentation Mismatches
- The top-level README and pipeline README describe a clean, phase-aligned architecture, and those docs are broadly coherent.
- However, the live runtime implementation does not fully match the idealized phase documentation for Phase 00 and some stale test import names do not match the current phase directories.
- The project-level architecture writes are cleaner than the live runtime and test harness, so the current repository is best described as documentation-idealized but implementation-uneven.

### Test Coverage Gaps
- Phase 00 has tests, but they are tied to website scraping details and network-like fetch behavior and are not as contract-focused as the phase architecture requires.
- Phase 01 has useful basic tests, but coverage is incomplete across all supported source types.
- Phase 02 has a broken import path (`phase_02_normalize`) and therefore cannot be trusted as working coverage.
- Phases 03–06 are under-covered relative to the claimed contract architecture, and the repeated test filename pattern across later phase directories causes pytest collection conflicts.
- The test suite does not adequately cover error-handling branches or canonicalization edge cases across phase boundaries.

### Architecture Violations
- The most important boundary violation is the legacy Phase 00 output naming drift: it does not use the canonical `raw_content` / `source_url` contract.
- The stale `phase_02_normalize` import names are a structural violation of the repository’s current naming and package layout.
- The duplicate test file basenames across phase test folders (`test_contracts.py`, `test_processor.py`, `test_runner.py`) are an architecture/test-harness violation and contribute to collection errors.
- The presence of stale logs and legacy field names indicates incomplete migration from earlier pipeline iterations.

---

## Priority Fix List

### Critical
- Fix Phase 00 output schema drift and restore the canonical source fields (`raw_content`, `source_url`) instead of `content` and `source`.
- Repair all stale phase 02 import paths and restore the test harness to a valid state.
- Resolve duplicate test module collisions across later phase test directories before any freeze or CI gate.

### High
- Reconcile the remaining legacy field names in debug logs and fixtures against the canonical contracts.
- Add missing contract tests for Phases 03–06 to lock the behavior and guard against gradual drift.
- Standardize debug artifact names and file shapes per phase.

### Medium
- Tighten edge-case coverage for character canonicalization, dialogue attribution, and voice mapping fallback logic.
- Improve metadata consistency and deterministic output formatting across all processors.
- Reduce doc/runtime drift between the architecture README and the implementation reality.

### Low
- Clean up legacy artifact names and old fixture directories that are no longer relevant to the current architecture.
- Simplify repository-level documentation so the phase responsibilities and exact output contracts are easier to compare against the runtime code.

---

## Freeze Recommendation

Phase 00: Not ready for freeze
Phase 01: Ready with minor fixes
Phase 02: Not ready for freeze
Phase 03: Ready with minor fixes
Phase 04: Ready with minor fixes
Phase 05: Ready with minor fixes
Phase 06: Ready with minor fixes

Overall recommendation: do not freeze the pipeline in its current state. The codebase has enough architectural structure to proceed, but the contract drift, stale test imports, and debug-artifact inconsistencies mean the build is not yet stable enough to act as a reliable baseline for downstream production work.

The minimum gate before freeze should be:
- complete Phase 00 contract cleanup,
- restoration of valid phase 02 tests,
- removal of duplicate/test-collision issues,
- and a pass of contract-focused validation for phases 03–06.
