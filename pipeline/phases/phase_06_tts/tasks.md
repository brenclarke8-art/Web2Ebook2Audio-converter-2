Phase 06 — Voice Assignment

Responsibility
- Voice mapping only.
- No character discovery.
- No semantic interpretation.

Inputs
- enriched_segments
- character_registry
- settings

Outputs
- voice_registry[] with fields:
  - voice_id
  - character_id
  - voice_role (narrator | character | fallback)
  - provider
  - voice_name
  - generation_settings
- voice_segments[] assignment map keyed by segment_id
- meta / input_summary / output_summary / errors / warnings / timings

Voice Modes
- manual: settings.tts.voice_mode = "manual"
  - explicit narrator and character voice mapping.
- adaptive: settings.tts.voice_mode = "adaptive"
  - placeholder extension points for profile-aware assignment.

Future TODOs
- adaptive voice assignment with emotion-aware TTS.
- provider-specific optimization and multi-provider fallback.
