Phase 04 — Character Registry

Responsibility
- First LLM-capable semantic phase boundary (current implementation may use deterministic placeholders).
- Book-wide entity discovery and canonicalization.

Inputs
- segments
- settings

Outputs
- character_registry[] with fields:
  - character_id
  - canonical_name
  - aliases
  - importance
  - first_seen_segment
  - character_profile (future expansion area)
- pass-through segments
- meta / input_summary / output_summary / errors / warnings / timings

Rules
- Emit canonical character IDs (char_###) for all downstream use.
- Replace legacy gender/entity/voice trait fields with character_profile.

Future TODOs
- Enrich character_profile with age/presentation/personality/tts_hints.
- Add relationship inference and cross-chapter consistency checks.
