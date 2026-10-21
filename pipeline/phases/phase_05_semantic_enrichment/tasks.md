Phase 05 — Semantic Enrichment

Responsibility
- Own story understanding and semantic attribution.
- Determine narration/dialogue/thought and attribution metadata.

Inputs
- segments
- character_registry
- settings

Outputs
- enriched_segments[] with fields:
  - segment_id
  - primary_type (narration | dialogue | thought)
  - speaker_id
  - thought_owner_id
  - pov_character_id
  - referenced_characters
  - emotion_tag
  - classification_confidence
  - speaker_confidence
- pass-through character_registry
- enrichment_stats
- meta / input_summary / output_summary / errors / warnings / timings

Rules
- Use Phase 03 text_markers as cues, not hard rules.
- Keep a single primary_type (no mixed content_types).
- All character references must use canonical character_id values.

Future TODOs
- Improve emotion detection.
- Add scene awareness and cross-segment speaker inference.
- Strengthen POV continuity tracking.
