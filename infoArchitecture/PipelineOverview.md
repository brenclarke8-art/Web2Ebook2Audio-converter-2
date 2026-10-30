# Pipeline Overview

## Purpose

The repository implements a contract-driven phase pipeline for turning source content into packaged audiobook artifacts.

## Execution Model

Each phase follows:

1. Input validation with Pydantic model
2. `process()` execution
3. Debug artifact writing
4. Dict return to the next phase

## Implemented Sequence

1. Phase 00 bootstrap (pre-fetch configuration)
2. Phase 00 fetch
3. Phase 01 source
4. Phase 02 cleaning
5. Phase 03 segmentation
6. Phase 04 character registry
7. Phase 05 semantic enrichment
8. Phase 06 voice assignment
9. Phase 07 contract implemented under `phase_08_timing`
10. Phase 08 contract implemented under `phase_09_packaging`
11. Phase 09 contract currently duplicated under `phase_10_validation`

## Boundary Rule

Only fetch performs network acquisition. Downstream phases are expected to be deterministic contract transforms, with export writing happening in the phase-09 contract implementation.
