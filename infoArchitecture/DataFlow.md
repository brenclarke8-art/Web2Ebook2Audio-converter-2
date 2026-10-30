# Data Flow

## Canonical Object Flow

- `Phase00FetchInput` -> `Phase00FetchOutput.source`
- `Phase01Input.source` -> `Phase01Output.chapter_index + raw_payloads`
- `Phase02Input.chapter_index/raw_payloads` -> `Phase02Output.normalized_chapters/chapter_stats`
- `Phase03Input.normalized_chapters` -> `Phase03Output.segments`
- `Phase04Input.segments` -> `Phase04Output.character_registry + segments`
- `Phase05Input.segments/character_registry` -> `Phase05Output.enriched_segments`
- `Phase06Input.enriched_segments/character_registry` -> `Phase06Output.voice_registry + voice_segments`
- `Phase07Input.audio_chunks/audio_index` -> `Phase07Output.stitched_audio + stitched_index`
- `Phase08Input.stitched_audio/stitched_index` -> `Phase08Output.package_manifest + package_index`
- `Phase09Input.package_manifest/package_index` -> `Phase09Output.export_manifest + export_index`

## Side Effects by Phase

- Phase 00 fetch: network reads and learned-rule persistence
- Phase 09 contract implementation (`phase_10_validation`): filesystem export writes
- Other phases: contract transformations + debug artifact writes via `debug.py`

## Shared Metadata Pattern

All outputs include:

- `meta`
- `input_summary`
- `output_summary`
- `errors`
- `warnings`
- `timings`
