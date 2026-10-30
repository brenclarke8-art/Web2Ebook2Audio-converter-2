# Design Decisions

## 1) Strict Runner Contract

Runners are intentionally thin and consistent across phases to keep orchestration behavior predictable and testable.

## 2) Schema-First Phase Interfaces

Every phase has explicit Pydantic input/output models to keep boundaries stable and auditable.

## 3) Canonical Character IDs

Character handling transitions from raw names to canonical `character_id` values, which downstream semantic and voice phases consume.

## 4) Layered Semantics

Structural segmentation (phase 03) is separated from semantic inference (phase 05), and voice mapping (phase 06) is separated from semantic inference.

## 5) Incremental Build-Out of Late Pipeline Phases

Phase contracts for 07/08/09 exist, but their folder names are offset (`phase_08_timing`, `phase_09_packaging`, `phase_10_validation`), and phase-10-specific validation contract is not yet distinct.
