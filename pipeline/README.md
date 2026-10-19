# Pipeline Architecture (Phase-Aligned)

## Final Pipeline

00 Fetch  
01 Source  
02 Cleaning  
03 Segmentation  
04 Character Registry  
05 Semantic Enrichment  
06 Voice Assignment  
07 TTS  
08 Timing  
09 Packaging  
10 Validation

## Phase Responsibilities

| Phase | Responsibility |
| --- | --- |
| 03 | Structural segmentation |
| 04 | Character discovery and canonicalization |
| 05 | Semantic attribution |
| 06 | Voice mapping |
| 07 | TTS generation |
| 08 | Timing/alignment |
| 09 | Packaging |
| 10 | Validation |

## Design Principles

- Single responsibility per phase.
- Canonical `character_id` usage across downstream phases.
- Partial-book processing support via `chapter_id` + `sequence` ordering.
- Deterministic structural phases before semantic/LLM-heavy phases.
- Future-compatible adaptive voice support.

## Schema Synchronization Notes (Phase 03–06)

- Phase 03 emits structural segments only; no speaker/entity semantics.
- Phase 04 emits canonical character registry with unified `character_profile`.
- Phase 05 emits single `primary_type` attribution and confidence metadata.
- Phase 06 emits voice registry + segment voice assignments with manual/adaptive mode support.

Removed fields from the active 03–06 contracts:
- `word_count`
- `char_count`
- `global_sequence`
- `content_types`
- `gender`
- `voice_profile`
- `character_traits`
- `entity_type`

## Future Deployment Roadmap

- **Phase 04 extensions**: richer profile inference (age/presentation/personality), relationship graphing, and profile confidence tracking.
- **Phase 05 extensions**: scene-aware attribution, POV persistence, stronger emotion modeling, and cross-segment speaker continuity.
- **Phase 06 extensions**: adaptive provider selection, emotion-aware rendering policies, and resilient multi-provider fallback routing.
- **Operational deployment**: promote schema contracts to versioned API docs and gate deployment on contract + integration snapshots.
