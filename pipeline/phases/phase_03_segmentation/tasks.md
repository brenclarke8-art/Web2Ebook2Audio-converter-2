Phase 03 — Segmentation

Responsibility
- Structural processing only.
- No LLM calls.
- No character identification.
- No speaker attribution.
- No semantic enrichment.

Inputs
- normalized_chapters: {chapter_id: cleaned chapter text}
- chapter_stats
- settings

Outputs
- segments[] with fields:
  - segment_id
  - chapter_id
  - sequence
  - paragraph_index
  - structural_type (paragraph | heading | scene_break | chapter_title)
  - text
  - text_markers (double_quote | single_quote | italicized)
  - source_offset_start
  - source_offset_end
- segmentation_stats
- meta / input_summary / output_summary / errors / warnings / timings

Rules
- Deterministic structural phase only.
- Ordering must be chapter-scoped by chapter_id + sequence.
- Do not emit global_sequence.
- Do not emit derived counters (word_count, char_count).
